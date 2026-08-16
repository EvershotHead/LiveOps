"""中文向量嵌入：bge-m3 → bge-small-zh → 字符 n-gram 哈希嵌入（降级链）。

降级必须记录 embed_quality，写入 manifest，报告如实呈现。
哈希嵌入确定性可测试，保证无重依赖时流水线仍可运行。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from . import config


@dataclass
class EmbedResult:
    vectors: list[list[float]]
    dim: int
    embed_quality: str   # "bge-m3" | "bge-small" | "hash-degraded"
    model_name: str


_FALLBACK_SMALL = "BAAI/bge-small-zh-v1.5"


def _hash_embed_one(text: str, dim: int = 256) -> list[float]:
    """字符三元组哈希嵌入：确定性、无依赖；仅作降级方案。"""
    vec = [0.0] * dim
    t = re.sub(r"\s+", "", text.lower())
    grams = [t[i : i + 3] for i in range(max(len(t) - 2, 1))] or [t]
    for g in grams:
        h = int.from_bytes(hashlib.md5(g.encode("utf-8")).digest()[:4], "big")
        vec[h % dim] += 1.0 if (h >> 31) & 1 else -1.0
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def embed_texts(texts: list[str], *, dim: int = 256) -> EmbedResult:
    """按降级链计算嵌入。任何异常都收敛为哈希降级，不中断流水线。"""
    wanted = config.EMBED_MODEL
    try:
        from sentence_transformers import SentenceTransformer
        try:
            model = SentenceTransformer(wanted)
            vecs = model.encode(texts, normalize_embeddings=True).tolist()
            return EmbedResult(vectors=vecs, dim=len(vecs[0]) if vecs else 0,
                               embed_quality="bge-m3", model_name=wanted)
        except Exception:
            if wanted != _FALLBACK_SMALL:
                model = SentenceTransformer(_FALLBACK_SMALL)
                vecs = model.encode(texts, normalize_embeddings=True).tolist()
                return EmbedResult(vectors=vecs, dim=len(vecs[0]) if vecs else 0,
                                   embed_quality="bge-small", model_name=_FALLBACK_SMALL)
            raise
    except Exception:
        return EmbedResult(
            vectors=[_hash_embed_one(t, dim) for t in texts],
            dim=dim, embed_quality="hash-degraded", model_name="hash-3gram",
        )
