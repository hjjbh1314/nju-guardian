"""
向量召回引擎 · D2 (2026-05-07)

设计目标：
- 在现有「关键词 + 正则」之外增加语义召回，覆盖换说法/同义词的边角输入。
- 默认使用 BAAI/bge-small-zh-v1.5（中文优化、95MB）；缺网/缺模型时自动降级到 TF-IDF。
- 知识库 hash 不变就用磁盘缓存；KB 改了重新索引一次。

调用示例：
    from embedding_engine import VectorEngine
    eng = VectorEngine(kb)
    eng.ensure_index()                     # 首次 ~10s，之后从缓存
    hits = eng.search("视频里朋友哭着借钱", top_k=5)
    # → [("KB-016", 0.62), ("KB-008", 0.51), ...]
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("NJU_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
CACHE_DIR = Path(__file__).parent / ".embeddings_cache"


@dataclass
class VectorHit:
    case_id: str
    similarity: float
    snippet: str = ""


def _case_to_corpus(case: dict) -> str:
    """把一条 case 拼成用于嵌入的语义文本。把核心语义信号都喂进去。"""
    parts = [
        case.get("name", ""),
        case.get("type", ""),
        " ".join(case.get("keywords", [])[:8]),
        " ".join(case.get("script_examples", [])),
        " ".join(case.get("why_scam", [])[:2]),
    ]
    return " | ".join(p for p in parts if p)


def _kb_signature(kb: dict) -> str:
    """KB 内容指纹 — 内容变了就让缓存失效。"""
    payload = json.dumps(
        [(c["id"], _case_to_corpus(c)) for c in kb.get("cases", [])],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class VectorEngine:
    """语义召回。优先 SBERT，失败降级 TF-IDF，再失败彻底跳过。"""

    def __init__(self, kb: dict, model_name: str = DEFAULT_MODEL):
        self.kb = kb
        self.model_name = model_name
        self.cases = kb.get("cases", [])
        self.case_ids = [c["id"] for c in self.cases]
        self.corpora = [_case_to_corpus(c) for c in self.cases]
        self._signature = _kb_signature(kb)
        self._mode: str = "uninitialized"  # sbert / tfidf / disabled
        self._model = None
        self._embeddings: np.ndarray | None = None
        self._tfidf_vec = None
        self._tfidf_mat = None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ public

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_available(self) -> bool:
        return self._mode in {"sbert", "tfidf"}

    def ensure_index(self) -> str:
        """构建/加载索引。返回最终 mode（sbert / tfidf / disabled）。"""
        if self._mode != "uninitialized":
            return self._mode
        try:
            self._init_sbert()
            self._mode = "sbert"
            logger.info("VectorEngine: 使用 SBERT 模型 %s", self.model_name)
        except Exception as e:
            logger.warning("VectorEngine: SBERT 初始化失败，降级到 TF-IDF — %s", e)
            try:
                self._init_tfidf()
                self._mode = "tfidf"
            except Exception as e2:
                logger.error("VectorEngine: TF-IDF 也初始化失败 — %s", e2)
                self._mode = "disabled"
        return self._mode

    def search(self, query: str, top_k: int = 5, min_sim: float = 0.0) -> list[VectorHit]:
        if not query or not query.strip() or self._mode == "disabled":
            return []
        if self._mode == "uninitialized":
            self.ensure_index()

        if self._mode == "sbert":
            sims = self._sbert_similarity(query)
        elif self._mode == "tfidf":
            sims = self._tfidf_similarity(query)
        else:
            return []

        idx_sorted = np.argsort(-sims)[:top_k]
        hits: list[VectorHit] = []
        for i in idx_sorted:
            sim = float(sims[i])
            if sim < min_sim:
                continue
            hits.append(
                VectorHit(
                    case_id=self.case_ids[i],
                    similarity=sim,
                    snippet=self.corpora[i][:80],
                )
            )
        return hits

    # ----------------------------------------------------------------- sbert

    def _init_sbert(self) -> None:
        """加载 SBERT 模型，构建/读取嵌入缓存。"""
        from sentence_transformers import SentenceTransformer

        cache_file = CACHE_DIR / f"sbert_{self.model_name.replace('/', '_')}_{self._signature}.npz"
        if cache_file.exists():
            logger.info("VectorEngine: 命中嵌入缓存 %s", cache_file.name)
            data = np.load(cache_file)
            self._embeddings = data["emb"]
            ids_in_cache = list(data["ids"])
            if ids_in_cache != self.case_ids:
                logger.warning("缓存 case_ids 与当前 KB 不一致，重新计算")
            else:
                self._model = SentenceTransformer(self.model_name)
                return

        # 重新计算
        self._model = SentenceTransformer(self.model_name)
        embeddings = self._model.encode(
            self.corpora,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=16,
        )
        self._embeddings = np.asarray(embeddings, dtype=np.float32)
        np.savez(cache_file, emb=self._embeddings, ids=np.array(self.case_ids))
        logger.info("VectorEngine: 已写入嵌入缓存 %s", cache_file.name)

    def _sbert_similarity(self, query: str) -> np.ndarray:
        q_emb = self._model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        # 归一化向量内积 = 余弦相似度
        return (self._embeddings @ q_emb[0]).astype(np.float32)

    # ----------------------------------------------------------------- tfidf

    def _init_tfidf(self) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._tfidf_vec = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            max_df=0.95,
            min_df=1,
        )
        self._tfidf_mat = self._tfidf_vec.fit_transform(self.corpora)

    def _tfidf_similarity(self, query: str) -> np.ndarray:
        from sklearn.metrics.pairwise import cosine_similarity

        q_vec = self._tfidf_vec.transform([query])
        sims = cosine_similarity(q_vec, self._tfidf_mat)[0]
        return sims.astype(np.float32)


# 简易冒烟测试入口
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    here = Path(__file__).parent
    with open(here / "knowledge_base.json", encoding="utf-8") as f:
        kb = json.load(f)

    eng = VectorEngine(kb)
    mode = eng.ensure_index()
    print(f"\n模式: {mode}\n")

    test_queries = [
        "视频里朋友哭着说手机被偷急用借钱",
        "保录哥伦比亚大学定金锁定offer",
        "向日葵远程协助让我帮你操作",
        "辅导员代收班费先给我转账",
        "群里说免费送礼品+点赞返佣金",
        "学姐毕业转让 MacBook Pro 半价",
        "助学金到账请到ATM按指示激活",
    ]
    for q in test_queries:
        hits = eng.search(q, top_k=3)
        print(f"Q: {q}")
        for h in hits:
            case = next(c for c in kb["cases"] if c["id"] == h.case_id)
            print(f"  {h.case_id}  sim={h.similarity:.3f}  {case['name']}")
        print()
