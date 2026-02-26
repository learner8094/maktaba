# services/semantic.py
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from config import CONFIG_DIR

SEM_DIR = os.path.join(CONFIG_DIR, "semantic")
DB_PATH = os.path.join(SEM_DIR, "semantic_index.sqlite3")
RUNTIME_DIR = os.path.join(SEM_DIR, "runtime")
VENV_DIR = os.path.join(RUNTIME_DIR, "venv")
WORKER_PATH = os.path.join(os.path.dirname(__file__), "semantic_worker.py")


class SemanticRuntime:
    """إدارة تجهيز بيئة venv الخاصة بالبحث الدلالي."""

    def __init__(self):
        self.model_name = os.environ.get("MAKTABA_EMBED_MODEL", "intfloat/multilingual-e5-small")

    @property
    def python_path(self) -> str:
        if os.name == "nt":
            return os.path.join(VENV_DIR, "Scripts", "python.exe")
        return os.path.join(VENV_DIR, "bin", "python")

    def _run(self, args: List[str], env: Optional[dict] = None):
        return subprocess.run(args, check=True, capture_output=True, text=True, env=env)

    def _format_install_error(self, raw_err: str) -> str:
        """تحويل أخطاء pip الطويلة لرسالة أوضح ومختصرة للمستخدم."""
        err = (raw_err or "").strip()
        low = err.lower()
        if "no matching distribution found" in low:
            return "تعذر تثبيت المتطلبات: لا توجد نسخة مناسبة لأحد الحزم على هذا النظام."
        if "could not install packages" in low or "failed building wheel" in low:
            return "تعذر تثبيت المتطلبات داخل البيئة الافتراضية. حاول تحديث النظام ثم أعد المحاولة."
        if "temporary failure in name resolution" in low or "connection" in low:
            return "تعذر تنزيل المتطلبات بسبب مشكلة اتصال بالإنترنت."
        if "permission denied" in low:
            return "تعذر تثبيت المتطلبات بسبب صلاحيات غير كافية."

        short = " ".join(err.splitlines()[-3:]).strip()
        return f"تعذر تجهيز البحث الدلالي: {short or 'خطأ غير معروف أثناء التثبيت.'}"

    def ensure_ready(self, progress_cb: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        def notify(msg: str):
            if progress_cb:
                progress_cb(msg)

        os.makedirs(RUNTIME_DIR, exist_ok=True)
        try:
            if not os.path.exists(self.python_path):
                notify("جاري إنشاء venv للبحث الدلالي لأول مرة...")
                self._run([sys.executable, "-m", "venv", VENV_DIR])

            notify("جاري التحقق من متطلبات البحث الدلالي (FAISS + E5)...")
            self._run([
                self.python_path,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
                "setuptools",
                "wheel",
                "faiss-cpu",
                "sentence-transformers",
            ])

            notify(f"جاري تحميل نموذج E5: {self.model_name} (إن لم يكن موجوداً)...")
            self._run([
                self.python_path,
                WORKER_PATH,
                "warmup",
                "--model",
                self.model_name,
            ])
            return True, f"تم تجهيز البحث الدلالي بنجاح: FAISS + E5 ({self.model_name})"
        except subprocess.CalledProcessError as e:
            err = (e.stderr or e.stdout or str(e)).strip()
            return False, self._format_install_error(err)


class EmbeddingBackend:
    def __init__(self):
        self.runtime = SemanticRuntime()
        self._name = None
        self._dim = None
        self._ready = False

    @property
    def available(self) -> bool:
        return bool(self._ready)

    @property
    def dim(self) -> int:
        return int(self._dim or 0)

    @property
    def name(self) -> str:
        return self._name or "غير متوفر"

    def ensure_ready(self, progress_cb: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        ok, msg = self.runtime.ensure_ready(progress_cb=progress_cb)
        if not ok:
            self._ready = False
            self._name = None
            self._dim = None
            return ok, msg

        try:
            sample = self.embed(["test"])
            self._dim = len(sample[0]) if sample else 0
            self._name = f"venv:sentence-transformers:{self.runtime.model_name}"
            self._ready = True
            return True, msg
        except Exception as e:
            self._ready = False
            self._name = None
            self._dim = None
            return False, f"تم تجهيز venv لكن فشل اختبار النموذج: {e}"

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self._ready:
            raise RuntimeError("Embedding backend غير متوفر: اضغط زر الشروع أولاً")

        payload = json.dumps({"model": self.runtime.model_name, "texts": texts}, ensure_ascii=False)
        cp = subprocess.run(
            [self.runtime.python_path, WORKER_PATH, "embed", "--payload", payload],
            check=True,
            capture_output=True,
            text=True,
        )
        out = json.loads(cp.stdout)
        return out.get("vectors", [])

    def rank_with_faiss(self, query_vec: List[float], vectors: List[List[float]], limit: int) -> List[Tuple[int, float]]:
        if not self._ready:
            raise RuntimeError("FAISS غير متوفر: اضغط زر الشروع أولاً")
        payload = json.dumps({"query": query_vec, "vectors": vectors, "limit": int(limit)}, ensure_ascii=False)
        cp = subprocess.run(
            [self.runtime.python_path, WORKER_PATH, "rank", "--payload", payload],
            check=True,
            capture_output=True,
            text=True,
        )
        out = json.loads(cp.stdout)
        return [(int(i), float(s)) for i, s in out.get("results", [])]


def _ensure_db():
    os.makedirs(SEM_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
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
    """
    )
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
            """,
            rows,
        )
        self._con.commit()

    def delete_for_part_if_mtime_changed(self, part_path: str, mtime: float):
        self._con.execute("DELETE FROM chunks WHERE part_path = ?", (part_path,))
        self._con.commit()

    def search_full(self, query: str, limit: int = 50, book_dir_filter: Optional[str] = None) -> List[SemanticResult]:
        if not self.backend.available:
            raise RuntimeError("Embedding backend غير متوفر")

        qv = self.backend.embed([query])[0]
        sql = "SELECT book_dir, part_path, part_idx, page_idx, title, text, dim, vec FROM chunks"
        params = []
        if book_dir_filter:
            sql += " WHERE book_dir = ?"
            params.append(book_dir_filter)

        rows = self._con.execute(sql, params).fetchall()
        if not rows:
            return []

        vecs = [_unpack_vec(blob, int(dim)) for _, _, _, _, _, _, dim, blob in rows]
        ranked = self.backend.rank_with_faiss(qv, vecs, limit)

        results: List[SemanticResult] = []
        for idx, score in ranked:
            book_dir, part_path, part_idx, page_idx, title, text, _dim, _blob = rows[idx]
            snip = (text[:260] + ("..." if len(text) > 260 else "")).strip()
            results.append(SemanticResult(book_dir, part_path, int(part_idx), int(page_idx), float(score), title or "", snip))
        return results

    def get_or_compute_page_vector(
        self,
        book_dir: str,
        part_path: str,
        part_idx: int,
        page_idx: int,
        title: str,
        text: str,
        mtime: float,
    ) -> List[float]:
        if not self.backend.available:
            raise RuntimeError("Embedding backend غير متوفر")

        cid = _chunk_id(part_path, page_idx, mtime)
        cur = self._con.execute("SELECT dim, vec FROM chunks WHERE chunk_id = ?", (cid,))
        row = cur.fetchone()
        if row:
            dim, blob = row
            return _unpack_vec(blob, dim)

        self._con.execute("DELETE FROM chunks WHERE part_path = ?", (part_path,))
        self._con.commit()

        vec = self.backend.embed([text])[0]
        dim = self.backend.dim or len(vec)
        self._con.execute(
            """INSERT OR REPLACE INTO chunks
               (chunk_id, book_dir, part_path, part_idx, page_idx, title, text, mtime, dim, vec)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (cid, book_dir, part_path, int(part_idx), int(page_idx), title, text, float(mtime), int(dim), _pack_vec(vec)),
        )
        self._con.commit()
        return vec
