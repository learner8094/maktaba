# services/utils_text.py
import re

AR_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")

def strip_diacritics(text: str) -> str:
    return AR_DIACRITICS_RE.sub("", text)

def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
