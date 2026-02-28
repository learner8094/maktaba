# services/search.py
import os
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import unquote

from config import RECOLL_DIR, BOOKS_DIR

@dataclass
class SearchHit:
    filepath: str
    line_num_1based: int
    display: str
    snippet: str

def _build_dir_filter(scope: str, scope_value: str) -> str:
    scope_value = (scope_value or "").strip()
    if scope == "قسم معين" and scope_value:
        d = os.path.join(BOOKS_DIR, scope_value)
        if os.path.exists(d):
            return f'dir:"{d}" AND '
    elif scope == "كتاب واحد" and scope_value:
        # scope_value قد يكون اسم مجلد الكتاب أو جزءًا من الاسم
        for root, dirs, _ in os.walk(BOOKS_DIR):
            for dn in dirs:
                if scope_value == dn or scope_value in dn:
                    d = os.path.join(root, dn)
                    return f'dir:"{d}" AND '
    return ""

def _normalize_query(query: str, match_mode: str) -> str:
    terms = [w for w in query.split() if w.strip()]
    if not terms:
        return ""

    if len(terms) == 1:
        return terms[0]

    op = "OR" if match_mode == "or" else "AND"
    return f" {op} ".join(terms)

def recoll_search(
    query: str,
    scope: str = "كل الكتب",
    scope_value: str = "",
    limit: int = 200,
    match_mode: str = "and",
) -> List[SearchHit]:
    query = (query or "").strip()
    if not query:
        return []

    normalized_query = _normalize_query(query, match_mode)
    if not normalized_query:
        return []

    cmd = ["recollq", "-c", RECOLL_DIR, "-A", "-g", str(limit)]
    dir_filter = _build_dir_filter(scope, scope_value)
    cmd.append(dir_filter + normalized_query)

    try:
        out = subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()
    except Exception as e:
        print(f"فشل في تنفيذ البحث: {e}")
        return []

    hits: List[SearchHit] = []
    current_file: Optional[str] = None
    in_snip = False

    for line in out:
        if "[file://" in line:
            m = re.search(r'\[(file://[^\]]+)\]', line)
            if m:
                current_file = unquote(m.group(1).replace("file://", ""))
            continue
        if line.strip() == "SNIPPETS":
            in_snip = True
            continue
        if line.strip() == "/SNIPPETS":
            in_snip = False
            continue
        if in_snip and re.match(r'^\d+\s*:\s*', line):
            if not current_file:
                continue
            ln, txt = line.split(":", 1)
            try:
                ln_i = int(ln.strip())
            except Exception:
                continue
            txt = txt.strip()

            book_dir = os.path.dirname(current_file)
            section = os.path.basename(os.path.dirname(book_dir))
            title = os.path.basename(book_dir)
            display = f"{section} | {title}"
            snippet = txt[:240] + ("..." if len(txt) > 240 else "")
            hits.append(SearchHit(current_file, ln_i, display, snippet))

    return hits
