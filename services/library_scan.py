# services/library_scan.py
import os
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from config import BOOKS_DIR

@dataclass(frozen=True)
class BookInfo:
    dir_path: str
    title: str
    author: str
    meta: dict
    mtime: float

def _safe_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0

def _load_meta(book_dir: str) -> Tuple[dict, float]:
    meta_path = os.path.join(book_dir, "meta.json")
    if not os.path.exists(meta_path):
        return {}, _safe_mtime(book_dir)
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f), _safe_mtime(meta_path)
    except Exception:
        return {}, _safe_mtime(meta_path)

def _pretty_name(folder: str) -> str:
    return folder.replace("_", " ").strip()

class LibraryScanner:
    """يمسح المكتبة مع كاش بسيط لتقليل قراءة meta.json"""
    def __init__(self):
        self._cache: Dict[str, BookInfo] = {}

    def refresh(self) -> Dict[str, List[BookInfo]]:
        """يعيد قاموسًا: {اسم_القسم: [BookInfo...]}"""
        result: Dict[str, List[BookInfo]] = {}

        if not os.path.exists(BOOKS_DIR):
            return result

        sections = sorted([d for d in os.listdir(BOOKS_DIR) if os.path.isdir(os.path.join(BOOKS_DIR, d))])
        for section in sections:
            sec_path = os.path.join(BOOKS_DIR, section)
            books: List[BookInfo] = []
            for entry in sorted(os.listdir(sec_path)):
                book_dir = os.path.join(sec_path, entry)
                if not os.path.isdir(book_dir):
                    continue

                meta, meta_mtime = _load_meta(book_dir)
                cached = self._cache.get(book_dir)
                if cached and abs(cached.mtime - meta_mtime) < 0.0001:
                    books.append(cached)
                    continue

                title = meta.get("title") or _pretty_name(entry)
                author = ""
                author_info = meta.get("author")
                if isinstance(author_info, dict):
                    author = author_info.get("name", "") or ""
                elif isinstance(author_info, str):
                    author = author_info

                info = BookInfo(
                    dir_path=book_dir,
                    title=_pretty_name(title),
                    author=_pretty_name(author),
                    meta=meta,
                    mtime=meta_mtime
                )
                self._cache[book_dir] = info
                books.append(info)

            if books:
                result[_pretty_name(section)] = books

        return result

    def total_books(self) -> int:
        libs = self.refresh()
        return sum(len(v) for v in libs.values())
