# services/indexing.py
import os
import subprocess
from typing import Optional, Tuple
from config import RECOLL_DIR, BOOKS_DIR

def ensure_recoll_config() -> None:
    """التأكد من وجود إعدادات Recoll صحيحة"""
    os.makedirs(RECOLL_DIR, exist_ok=True)
    conf_file = os.path.join(RECOLL_DIR, "recoll.conf")
    if not os.path.exists(conf_file):
        with open(conf_file, "w", encoding="utf-8") as f:
            f.write(f"topdirs = {BOOKS_DIR}\n")
            f.write("defaultcharset = utf-8\n")

def get_recoll_db_mtime() -> float:
    db_file = os.path.join(RECOLL_DIR, "xapiandb", "flintlock")
    if not os.path.exists(db_file):
        return 0.0
    try:
        return os.path.getmtime(db_file)
    except Exception:
        return 0.0

def get_books_latest_mtime() -> float:
    latest = 0.0
    if not os.path.exists(BOOKS_DIR):
        return latest
    for root, _, files in os.walk(BOOKS_DIR):
        for fn in files:
            if fn.lower().endswith((".html", ".htm", ".xhtml", ".json")):
                p = os.path.join(root, fn)
                try:
                    latest = max(latest, os.path.getmtime(p))
                except Exception:
                    pass
    return latest

def needs_reindex(grace_seconds: int = 1) -> bool:
    """التحقق من الحاجة لإعادة الفهرسة (مرة عند فتح البرنامج)"""
    ensure_recoll_config()
    db_mtime = get_recoll_db_mtime()
    if db_mtime <= 0:
        return True
    books_mtime = get_books_latest_mtime()
    return books_mtime > db_mtime + grace_seconds

def run_recollindex() -> Tuple[bool, Optional[str]]:
    """تشغيل recollindex وإرجاع (نجاح، رسالة خطأ إن وجدت)"""
    ensure_recoll_config()
    try:
        subprocess.run(
            ["recollindex", "-c", RECOLL_DIR],
            check=True,
            capture_output=True,
            text=True
        )
        return True, None
    except Exception as e:
        err = getattr(e, "stderr", None)
        if isinstance(err, str) and err.strip():
            return False, err.strip()
        return False, str(e)
