# services/semantic.py
import os
import sqlite3
import hashlib
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple, Dict

import math

from config import CONFIG_DIR

SEM_DIR = os.path.join(CONFIG_DIR, "semantic")
DB_PATH = os.path.join(SEM_DIR, "semantic_index.sqlite3")

# ──────────────────────────────────────────────
# Embedding backend (اختياري)
# ──────────────────────────────────────────────
class EmbeddingBackend:
    def __init__(self):
        self._backend = None
        self._dim = None
        self._name = None
        self._init_backend()

    @property
    def available(self) -> bool:
        return self._backend is not None

    @property
    def dim(self) -> int:
        return int(self._dim or 0)

    @property
    def name(self) -> str:
        return self._name or "غير متوفر"

    def _init_backend(self):
        # 1) fastembed (خفيف غالبًا)
        try:
            from fastembed import TextEmbedding
            model_name = os.environ.get("MAKTABA_EMBED_MODEL", "intfloat/multilingual-e5-small")
            self._backend = TextEmbedding(model_name=model_name)
            self._name = f"fastembed:{model_name}"
            # fastembed لا يصرّح dim مباشرة بسهولة: نستنتجها بأول تضمين
            test = next(iter(self._backend.embed(["test"])))
            self._dim = len(test)
            return
        except Exception:
            self._backend = None

        # 2) sentence-transformers (قد يحتاج torch وهو أثقل)
        try:
            from sentence_transformers import SentenceTransformer
            model_name = os.environ.get("MAKTABA_EMBED_MODEL", "intfloat/multilingual-e5-small")
            self._backend = SentenceTransformer(model_name)
            self._name = f"sentence-transformers:{model_name}"
            self._dim = int(getattr(self._backend, "get_sentence_embedding_dimension")())
            return
        except Exception:
            self._backend = None
            self._name = None
            self._dim = None

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.available:
            raise RuntimeError("Embedding backend غير متوفر")
        # fastembed
        if hasattr(self._backend, "embed"):
            try:
                vecs = list(self._backend.embed(texts))
                return [list(map(float, v)) for v in vecs]
            except TypeError:
                pass
        # sentence-transformers
        if hasattr(self._backend, "encode"):
            vecs = self._backend.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return [list(map(float, v)) for v in vecs]
        raise RuntimeError("Backend غير مدعوم")

def _ensure_db():
    os.makedirs(SEM_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            book_dir TEXT NOT NULL,
            part_path TEXT NOT NULL,
            part_idx INTEGER NOT NULL,
            page_idx INTEGER NOT NULL,
            title TEXT,
            text TEXT,
            mtime REAL NOT NULL,
            dim INTEGER NOT NULL,
            vec BLOB NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_book_dir ON chunks(book_dir)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_part_path ON chunks(part_path)")
    con.commit()
    return con

def _chunk_id(part_path: str, page_idx: int, mtime: float) -> str:
    h = hashlib.sha1(f"{part_path}|{page_idx}|{mtime}".encode("utf-8", errors="ignore")).hexdigest()
    return h

def _pack_vec(vec: List[float]) -> bytes:
    import struct
    return struct.pack(f"<{len(vec)}f", *vec)

def _unpack_vec(blob: bytes, dim: int) -> List[float]:
    import struct
    return list(struct.unpack(f"<{dim}f", blob))

def _cosine(a: List[float], b: List[float]) -> float:
    # افتراض: المتجهات قد تكون مُطبّعة (normalized)، لكن لا نعتمد ذلك.
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / math.sqrt(na * nb)

@dataclass
class SemanticResult:
    book_dir: str
    part_path: str
    part_idx: int
    page_idx: int
    score: float
    title: str
    snippet: str

class SemanticIndex:
    def __init__(self, backend: Optional[EmbeddingBackend] = None):
        self.backend = backend or EmbeddingBackend()
        self._con = _ensure_db()

    def close(self):
        try:
            self._con.close()
        except Exception:
            pass

    def backend_available(self) -> bool:
        return self.backend.available

    def upsert_chunks(self, chunks: List[Tuple[str, str, int, int, str, str, float]]):
        """chunks: [(book_dir, part_path, part_idx, page_idx, title, text, mtime)]"""
        if not chunks:
            return
        if not self.backend.available:
            raise RuntimeError("Embedding backend غير متوفر")

        texts = [c[5] for c in chunks]
        vecs = self.backend.embed(texts)
        dim = self.backend.dim or (len(vecs[0]) if vecs else 0)

        rows = []
        for (book_dir, part_path, part_idx, page_idx, title, text, mtime), vec in zip(chunks, vecs):
            cid = _chunk_id(part_path, page_idx, mtime)
            rows.append((cid, book_dir, part_path, part_idx, page_idx, title, text, mtime, dim, _pack_vec(vec)))

        self._con.executemany(
            """INSERT OR REPLACE INTO chunks
               (chunk_id, book_dir, part_path, part_idx, page_idx, title, text, mtime, dim, vec)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows
        )
        self._con.commit()

    def delete_for_part_if_mtime_changed(self, part_path: str, mtime: float):
        # إن تغيّر mtime، قد تتغير chunk_ids، فنحذف كل ما يخص هذا الملف ونُعيد إدراجه.
        # إن لم يكن موجودًا شيء، لا مشكلة.
        self._con.execute("DELETE FROM chunks WHERE part_path = ?", (part_path,))
        self._con.commit()

    def has_any(self) -> bool:
        cur = self._con.execute("SELECT 1 FROM chunks LIMIT 1")
        return cur.fetchone() is not None

    def search_full(self, query: str, limit: int = 50, book_dir_filter: Optional[str] = None) -> List[SemanticResult]:
        if not self.backend.available:
            raise RuntimeError("Embedding backend غير متوفر")
        qv = self.backend.embed([query])[0]

        sql = "SELECT book_dir, part_path, part_idx, page_idx, title, text, dim, vec FROM chunks"
        params = []
        if book_dir_filter:
            sql += " WHERE book_dir = ?"
            params.append(book_dir_filter)

        cur = self._con.execute(sql, params)
        results: List[SemanticResult] = []
        for book_dir, part_path, part_idx, page_idx, title, text, dim, blob in cur.fetchall():
            vec = _unpack_vec(blob, dim)
            score = _cosine(qv, vec)
            snip = (text[:260] + ("..." if len(text) > 260 else "")).strip()
            results.append(SemanticResult(book_dir, part_path, int(part_idx), int(page_idx), float(score), title or "", snip))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def get_or_compute_page_vector(self, book_dir: str, part_path: str, part_idx: int, page_idx: int,
                                   title: str, text: str, mtime: float) -> List[float]:
        if not self.backend.available:
            raise RuntimeError("Embedding backend غير متوفر")

        # محاولة استرجاعه
        cid = _chunk_id(part_path, page_idx, mtime)
        cur = self._con.execute("SELECT dim, vec FROM chunks WHERE chunk_id = ?", (cid,))
        row = cur.fetchone()
        if row:
            dim, blob = row
            return _unpack_vec(blob, dim)

        # إذا لم يوجد: نحذف كل القديم لهذا الملف ثم نضيف هذا المقطع (كاش بسيط)
        # (لأن mtime تغيّر غالبًا)
        self._con.execute("DELETE FROM chunks WHERE part_path = ?", (part_path,))
        self._con.commit()

        vec = self.backend.embed([text])[0]
        dim = self.backend.dim or len(vec)
        self._con.execute(
            """INSERT OR REPLACE INTO chunks
               (chunk_id, book_dir, part_path, part_idx, page_idx, title, text, mtime, dim, vec)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (cid, book_dir, part_path, int(part_idx), int(page_idx), title, text, float(mtime), int(dim), _pack_vec(vec))
        )
        self._con.commit()
        return vec
