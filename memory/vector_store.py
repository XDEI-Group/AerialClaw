"""
memory/vector_store.py — AerialClaw 轻量向量存储

优先使用 chromadb + sentence-transformers，不可用时自动降级：
  - 存储后端：chromadb → 纯内存（持久化到 vector_cache.json）
  - Embedding：sentence-transformers → 手写 TF-IDF
"""

from __future__ import annotations

import json
import math
import threading
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.errors import MemoryRetrievalError, MemoryStoreError
from core.logger import get_logger

logger = get_logger("memory.vector_store")

_CACHE_PATH = Path(__file__).parent / "vector_cache.json"


# ── 数据结构 ──────────────────────────────────────────────────

@dataclass
class MemoryItem:
    """向量存储检索结果"""
    memory_id: str
    text: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Embedding 后端 ────────────────────────────────────────────

class _SentenceTransformerEmbedder:
    """sentence-transformers 嵌入（首选）"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # type: ignore
        self._model = SentenceTransformer(model_name)
        logger.info(f"Embedding 后端：sentence-transformers ({model_name})")

    def embed(self, texts: List[str]) -> List[List[float]]:
        vecs = self._model.encode(texts, show_progress_bar=False)
        return vecs.tolist()


class _TFIDFEmbedder:
    """手写 TF-IDF 嵌入（降级后端，无额外依赖）"""

    def __init__(self):
        self._vocab: Dict[str, int] = {}
        self._df: Dict[str, int] = {}       # document frequency
        self._n_docs: int = 0
        self._lock = threading.Lock()
        logger.warning("Embedding 后端降级：手写 TF-IDF（语义精度有限）")

    # ── 公共接口 ──

    def embed(self, texts: List[str]) -> List[List[float]]:
        with self._lock:
            for t in texts:
                self._update_vocab(t)
            return [self._tfidf(t) for t in texts]

    # ── 内部 ──

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        import re
        return re.findall(r"[a-z\u4e00-\u9fff]+", text.lower())

    def _update_vocab(self, text: str) -> None:
        tokens = set(self._tokenize(text))
        for t in tokens:
            if t not in self._vocab:
                self._vocab[t] = len(self._vocab)
            self._df[t] = self._df.get(t, 0) + 1
        self._n_docs += 1

    def _tfidf(self, text: str) -> List[float]:
        tokens = self._tokenize(text)
        tf: Dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = max(len(tokens), 1)

        dim = len(self._vocab)
        vec = [0.0] * dim
        for t, cnt in tf.items():
            if t in self._vocab:
                idx = self._vocab[t]
                n = max(self._n_docs, 1)
                df = self._df.get(t, 1)
                idf = math.log((n + 1) / (df + 1)) + 1
                vec[idx] = (cnt / total) * idf

        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


def _build_embedder():
    """优先 sentence-transformers，超时/网络不通时降级到 TF-IDF。"""
    import os
    if os.environ.get("VECTOR_STORE_TFIDF_ONLY"):
        logger.info("环境变量 VECTOR_STORE_TFIDF_ONLY 已设置，直接用 TF-IDF")
        return _TFIDFEmbedder()
    try:
        import signal
        def _timeout_handler(signum, frame):
            raise TimeoutError("sentence-transformers 加载超时")
        old = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(10)  # 10秒超时
        try:
            result = _SentenceTransformerEmbedder()
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
            return result
        except Exception:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
            raise
    except Exception as e:
        logger.warning(f"sentence-transformers 不可用，降级到 TF-IDF：{e}")
        return _TFIDFEmbedder()


# ── 余弦相似度（numpy / 纯 Python）────────────────────────────

def _cosine(a: List[float], b: List[float]) -> float:
    """余弦相似度，优先 numpy，否则纯 Python"""
    try:
        import numpy as np  # type: ignore
        va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        return float(np.dot(va, vb) / denom) if denom else 0.0
    except ImportError:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (na * nb)


# ── 存储后端 ──────────────────────────────────────────────────

class _ChromaBackend:
    """chromadb 存储后端"""

    def __init__(self, collection: str):
        import chromadb  # type: ignore
        self._client = chromadb.Client()
        self._col = self._client.get_or_create_collection(collection)
        logger.info(f"存储后端：chromadb（collection={collection}）")

    def add(self, memory_id: str, text: str, embedding: List[float], metadata: dict) -> None:
        self._col.add(
            ids=[memory_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata or {}],
        )

    def query(self, embedding: List[float], top_k: int) -> List[tuple[str, str, float, dict]]:
        """返回 (id, text, score, metadata) 列表"""
        n = min(top_k, self._col.count())
        if n == 0:
            return []
        res = self._col.query(query_embeddings=[embedding], n_results=n)
        items = []
        for mid, doc, dist, meta in zip(
            res["ids"][0],
            res["documents"][0],
            res["distances"][0],
            res["metadatas"][0],
        ):
            score = 1.0 - dist  # chroma 默认 L2，转为相似度近似
            items.append((mid, doc, score, meta or {}))
        return items

    def delete(self, memory_id: str) -> None:
        self._col.delete(ids=[memory_id])

    def update(self, memory_id: str, text: str, embedding: List[float]) -> None:
        self._col.update(ids=[memory_id], documents=[text], embeddings=[embedding])

    def count(self) -> int:
        return self._col.count()

    def clear(self) -> None:
        self._col.delete(where={})  # delete all


class _MemoryBackend:
    """纯内存存储后端，支持 JSON 持久化"""

    def __init__(self, collection: str):
        self._collection = collection
        # {id: {"text": str, "embedding": list, "metadata": dict}}
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._cache_path = _CACHE_PATH
        self._load()
        logger.warning(f"存储后端降级：纯内存（collection={collection}，持久化到 {self._cache_path}）")

    # ── 持久化 ──

    def _load(self) -> None:
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
                self._store = data.get(self._collection, {})
                logger.debug(f"已从 {self._cache_path} 恢复 {len(self._store)} 条记忆")
            except Exception as e:
                logger.warning(f"加载向量缓存失败，清空：{e}")
                self._store = {}

    def _save(self) -> None:
        try:
            existing: Dict[str, Any] = {}
            if self._cache_path.exists():
                existing = json.loads(self._cache_path.read_text(encoding="utf-8"))
            existing[self._collection] = self._store
            self._cache_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"向量缓存保存失败：{e}")

    # ── 接口 ──

    def add(self, memory_id: str, text: str, embedding: List[float], metadata: dict) -> None:
        with self._lock:
            self._store[memory_id] = {
                "text": text,
                "embedding": embedding,
                "metadata": metadata or {},
            }
            self._save()

    def query(self, embedding: List[float], top_k: int) -> List[tuple[str, str, float, dict]]:
        with self._lock:
            scored = []
            for mid, entry in self._store.items():
                stored_emb = entry["embedding"]
                # 长度对齐（TF-IDF 维度可能变化）
                min_len = min(len(embedding), len(stored_emb))
                score = _cosine(embedding[:min_len], stored_emb[:min_len])
                scored.append((mid, entry["text"], score, entry["metadata"]))
            scored.sort(key=lambda x: x[2], reverse=True)
            return scored[:top_k]

    def delete(self, memory_id: str) -> None:
        with self._lock:
            self._store.pop(memory_id, None)
            self._save()

    def update(self, memory_id: str, text: str, embedding: List[float]) -> None:
        with self._lock:
            if memory_id in self._store:
                self._store[memory_id]["text"] = text
                self._store[memory_id]["embedding"] = embedding
                self._save()

    def count(self) -> int:
        with self._lock:
            return len(self._store)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._save()


def _build_backend(collection: str) -> _ChromaBackend | _MemoryBackend:
    try:
        return _ChromaBackend(collection)
    except Exception as e:
        logger.warning(f"chromadb 不可用，降级到纯内存：{e}")
        return _MemoryBackend(collection)


# ── 主类 ─────────────────────────────────────────────────────

class VectorStore:
    """
    轻量向量存储。

    优先 chromadb + sentence-transformers；不可用时自动降级到
    纯内存（numpy cosine）+ 手写 TF-IDF，并持久化到 JSON。
    """

    def __init__(self, collection: str = "memory"):
        self._lock = threading.Lock()
        self._embedder = _build_embedder()
        self._backend = _build_backend(collection)

    # ── 公共接口 ──────────────────────────────────────────────

    def add(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        添加文本到向量存储。

        Args:
            text:     要存储的文本内容
            metadata: 附加元数据（可选）

        Returns:
            memory_id: 唯一标识符

        Raises:
            MemoryStoreError: 存储失败时
        """
        try:
            memory_id = str(uuid.uuid4())
            embedding = self._embedder.embed([text])[0]
            self._backend.add(memory_id, text, embedding, metadata or {})
            logger.debug(f"[VectorStore] 已添加 id={memory_id[:8]}…")
            return memory_id
        except Exception as e:
            raise MemoryStoreError(
                f"向量存储写入失败：{e}",
                fix_hint="检查磁盘空间或 chromadb 状态",
            ) from e

    def search(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """
        语义搜索，返回最相关的条目。

        Args:
            query: 查询文本
            top_k: 返回条目数上限

        Returns:
            按相关度降序排列的 MemoryItem 列表

        Raises:
            MemoryRetrievalError: 检索失败时
        """
        try:
            embedding = self._embedder.embed([query])[0]
            results = self._backend.query(embedding, top_k)
            return [
                MemoryItem(memory_id=mid, text=txt, score=score, metadata=meta)
                for mid, txt, score, meta in results
            ]
        except Exception as e:
            raise MemoryRetrievalError(
                f"向量检索失败：{e}",
                fix_hint="确认向量存储已初始化且非空",
            ) from e

    def delete(self, memory_id: str) -> None:
        """删除指定条目。"""
        try:
            self._backend.delete(memory_id)
            logger.debug(f"[VectorStore] 已删除 id={memory_id[:8]}…")
        except Exception as e:
            raise MemoryStoreError(f"删除记忆失败：{e}") from e

    def update(self, memory_id: str, text: str) -> None:
        """更新指定条目的文本（同时刷新 embedding）。"""
        try:
            embedding = self._embedder.embed([text])[0]
            self._backend.update(memory_id, text, embedding)
            logger.debug(f"[VectorStore] 已更新 id={memory_id[:8]}…")
        except Exception as e:
            raise MemoryStoreError(f"更新记忆失败：{e}") from e

    def count(self) -> int:
        """返回存储条目总数。"""
        return self._backend.count()

    def clear(self) -> None:
        """清空所有条目。"""
        self._backend.clear()
        logger.info("[VectorStore] 已清空")
