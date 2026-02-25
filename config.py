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

def load_config() -> dict:
    """تحميل الإعدادات من ملف JSON"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg: dict):
    """حفظ الإعدادات في ملف JSON"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
