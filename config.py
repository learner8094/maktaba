# config.py
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOOKS_DIR = os.path.join(BASE_DIR, "books")
RECOLL_DIR = os.path.join(BASE_DIR, ".recoll")
STYLE_FILE = os.path.join(BASE_DIR, "style.css")  # تمت الإضافة
PAGE_LINES = 16
QURAN_FILE = os.path.join(BOOKS_DIR, "quran.xhtml")
QURAN_PAGE_WORDS = 80
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "recoll-gtk")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "font_size": 22,
    "quran_font_size": 22,
    "quran_page_words": QURAN_PAGE_WORDS,
    "reader_sidebar_width": 240,
    "auto_reindex_on_startup": True,
    "theme_mode": "dark",
}


def _sanitize_config(cfg: dict) -> dict:
    """توحيد القيم الحرجة والتأكد من وجودها ضمن المجال المنطقي."""
    merged = {**DEFAULT_CONFIG, **(cfg or {})}

    int_ranges = {
        "font_size": (14, 60),
        "quran_font_size": (12, 48),
        "quran_page_words": (40, 200),
        "reader_sidebar_width": (180, 420),
    }
    for key, (min_v, max_v) in int_ranges.items():
        try:
            merged[key] = int(merged.get(key, DEFAULT_CONFIG[key]))
        except (TypeError, ValueError):
            merged[key] = DEFAULT_CONFIG[key]
        merged[key] = max(min_v, min(max_v, merged[key]))

    merged["auto_reindex_on_startup"] = bool(merged.get("auto_reindex_on_startup", True))
    if merged.get("theme_mode") not in {"light", "dark", "dim"}:
        merged["theme_mode"] = DEFAULT_CONFIG["theme_mode"]
    return merged

def load_config() -> dict:
    """تحميل الإعدادات من ملف JSON"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return _sanitize_config(json.load(f))
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_config(cfg: dict):
    """حفظ الإعدادات في ملف JSON"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    cfg = _sanitize_config(cfg)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
