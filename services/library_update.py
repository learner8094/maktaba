import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request

from config import BASE_DIR, BOOKS_DIR


@dataclass
class LibraryUpdateResult:
    added_books: int
    skipped_books: int
    downloaded_files: int


class LibraryUpdater:
    """تحديث الكتب من GitHub (مجلد books) إلى مجلد books المحلي."""

    def __init__(self, repo: Optional[str] = None, branch: str = "main"):
        self.repo = repo or os.environ.get("MAKTABA_GITHUB_REPO", "maktaba/maktaba")
        self.branch = os.environ.get("MAKTABA_GITHUB_BRANCH", branch)

    def _api_url(self, path: str) -> str:
        encoded_path = quote(path)
        return (
            f"https://api.github.com/repos/{self.repo}/contents/{encoded_path}"
            f"?ref={quote(self.branch)}"
        )

    def _read_json(self, url: str):
        req = Request(url, headers={"Accept": "application/vnd.github+json"})
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _download_bytes(self, url: str) -> bytes:
        req = Request(url)
        with urlopen(req, timeout=30) as resp:
            return resp.read()

    def _list_dir(self, path: str) -> List[Dict]:
        data = self._read_json(self._api_url(path))
        if isinstance(data, dict) and data.get("type") == "file":
            return [data]
        return data

    def _resolve_root_items(self) -> List[Dict]:
        """يحاول الوصول إلى books مع مراعاة اختلاف اسم الفرع (main/master)."""
        tried_branches = []
        branch_candidates = [self.branch]
        if self.branch != "main":
            branch_candidates.append("main")
        if self.branch != "master":
            branch_candidates.append("master")

        last_error: Optional[Exception] = None
        for candidate in branch_candidates:
            self.branch = candidate
            tried_branches.append(candidate)
            try:
                return self._list_dir("books")
            except HTTPError as e:
                if e.code != 404:
                    raise
                last_error = e

        raise RuntimeError(
            "تعذر العثور على مجلد books في GitHub. "
            f"تحقق من MAKTABA_GITHUB_REPO='{self.repo}' و"
            f" MAKTABA_GITHUB_BRANCH (جرّبنا: {', '.join(tried_branches)})."
        ) from last_error

    def update_new_books(self) -> LibraryUpdateResult:
        added_books = 0
        skipped_books = 0
        downloaded_files = 0

        os.makedirs(BOOKS_DIR, exist_ok=True)

        root_items = self._resolve_root_items()
        for section in root_items:
            if section.get("type") != "dir":
                continue

            section_name = section["name"]
            section_local = os.path.join(BOOKS_DIR, section_name)
            os.makedirs(section_local, exist_ok=True)

            for book in self._list_dir(f"books/{section_name}"):
                if book.get("type") != "dir":
                    continue

                book_name = book["name"]
                local_book_dir = os.path.join(section_local, book_name)

                if os.path.exists(local_book_dir):
                    skipped_books += 1
                    continue

                os.makedirs(local_book_dir, exist_ok=True)
                files = self._list_dir(f"books/{section_name}/{book_name}")

                for item in files:
                    if item.get("type") != "file":
                        continue
                    dl_url = item.get("download_url")
                    if not dl_url:
                        continue

                    content = self._download_bytes(dl_url)
                    local_file = os.path.join(local_book_dir, item["name"])
                    with open(local_file, "wb") as f:
                        f.write(content)
                    downloaded_files += 1

                added_books += 1

        return LibraryUpdateResult(
            added_books=added_books,
            skipped_books=skipped_books,
            downloaded_files=downloaded_files,
        )

    def update_new_books_safe(self) -> LibraryUpdateResult:
        try:
            return self.update_new_books()
        except (HTTPError, URLError) as e:
            raise RuntimeError(f"تعذر الاتصال بواجهة GitHub: {e}") from e
        except Exception as e:
            raise RuntimeError(f"فشل تحديث المكتبة: {e}") from e
