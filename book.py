# book.py
import os
import re
import json
from html.parser import HTMLParser
from config import PAGE_LINES, QURAN_PAGE_WORDS

class HTMLExtractor(HTMLParser):
    """يستخرج النصوص والفصول من HTML مع دعم الهيكلية والقوائم"""
    def __init__(self):
        super().__init__()
        self.lines = []
        self.sections = [] # (title, line_index, level)
        self.line_to_page = {}
        self.page_break_line_idxs = []
        self.current_page_num = None
        self._line = 0
        self._in_h = False
        self._h_level = 0
        self._in_title_span = False
        self._in_page_number = False
        self._in_li = False 

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "span":
            classes = (attrs_dict.get("class") or "").split()
            if "page-break-marker" in classes:
                self.page_break_line_idxs.append(self._line)

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_h = True
            try:
                self._h_level = int(tag[1])
            except:
                self._h_level = 1
        
        if tag == "li":
            self._in_li = True

        if tag == "span":
            class_attr = attrs_dict.get("class", "")
            if "title" in class_attr:
                self._in_title_span = True
            if "PageNumber" in class_attr.split():
                self._in_page_number = True

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_h = False
            self._h_level = 0
        if tag == "span":
            self._in_title_span = False
            self._in_page_number = False
        if tag == "li":
            self._in_li = False

    def handle_data(self, data):
        t = data.strip()
        t = t.replace('\u200c', '').strip() 
        
        if not t:
            return
            
        if self._in_page_number:
            self.current_page_num = t
        else:
            if self._in_li:
                t = f"• {t}"

            if self._in_h:
                self.sections.append((t, self._line, self._h_level))
            elif self._in_title_span:
                self.sections.append((t, self._line, 2))
            
            self.lines.append(t)
            if self.current_page_num:
                self.line_to_page[self._line] = self.current_page_num
            self._line += 1

class BookPart:
    """يمثل جزء واحد من الكتاب (ملف HTML)"""
    def __init__(self, path):
        self.path = path
        self.is_quran = "quran" in os.path.basename(path).lower()
        self.lines = []
        self.sections = []
        self.pages = []
        self.page_first_line_idxs = [] 
        self.line_to_page = {}
        self.line_to_page_index = {}
        self.page_break_line_idxs = []
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8", errors="ignore") as f:
                html = f.read()
            if self.is_quran:
                suras = re.findall(
                    r'<div class="sura" data-sura="(\d+)">.*?<div class="sura-title">(.*?)</div>(.*?)</div>',
                    html, re.DOTALL
                )
                self.lines = []
                self.sections = []
                for sura_num, sura_name, content in suras:
                    clean_name = sura_name.strip().replace("سورة ", "", 1).strip()
                    line_idx = len(self.lines)
                    # القرآن مستوى واحد
                    self.sections.append((clean_name, line_idx, 1))
                    self.lines.append("\n") 
                    self.lines.append(f"سورة {clean_name}")
                    self.lines.append("\n")
                    ayas = re.findall(r'<span class="aya" data-aya="(\d+)">(.*?)</span>', content, re.DOTALL)
                    for aya_num, text in ayas:
                        self.lines.append(f"{text.strip()} ({aya_num})")
                self.paginate()
            else:
                extractor = HTMLExtractor()
                extractor.feed(html)
                self.lines = extractor.lines
                self.sections = extractor.sections
                self.line_to_page = extractor.line_to_page
                self.page_break_line_idxs = extractor.page_break_line_idxs
                self.paginate()
        except Exception as e:
            print(f"فشل في تحميل الجزء: {e}")

    def paginate(self):
        self.pages = []
        self.page_first_line_idxs = []
        
        if not self.is_quran:
            if self.page_break_line_idxs:
                breakpoints = sorted({
                    idx for idx in self.page_break_line_idxs
                    if 0 < idx < len(self.lines)
                })
                starts = [0] + breakpoints

                for page_idx, start in enumerate(starts):
                    end = breakpoints[page_idx] if page_idx < len(breakpoints) else len(self.lines)
                    self.page_first_line_idxs.append(start)
                    self.pages.append("\n".join(self.lines[start:end]))
                    for line_idx in range(start, end):
                        self.line_to_page_index[line_idx] = page_idx
                return

            # تقسيم النص إلى صفحات ثابتة بعدد أسطر محدد (PAGE_LINES)
            # مع إنشاء خريطة line_to_page_index لتمكين الانتقال الدقيق لعناوين الفصول.
            joiner = "\n"
            self.line_to_page_index = {}
            for page_idx, i in enumerate(range(0, len(self.lines), PAGE_LINES)):
                self.page_first_line_idxs.append(i)
                page_content = joiner.join(self.lines[i:i + PAGE_LINES])
                self.pages.append(page_content)
                end = min(i + PAGE_LINES, len(self.lines))
                for line_idx in range(i, end):
                    self.line_to_page_index[line_idx] = page_idx
            return

        current_page = []
        current_word_count = 0
        current_line_idx = 0
        page_start_idx = 0

        for line_idx, line in enumerate(self.lines):
            if not current_page:
                page_start_idx = line_idx

            if line.strip() == "" or line.startswith("سورة "):
                current_page.append(line)
            else:
                words = line.split()
                word_count = len(words)
                if current_word_count + word_count > QURAN_PAGE_WORDS and current_page:
                    self.pages.append(" ".join(current_page))
                    self.page_first_line_idxs.append(page_start_idx)
                    
                    for prev_line in range(page_start_idx, line_idx):
                        self.line_to_page_index[prev_line] = len(self.pages) - 1
                    
                    current_page = [line]
                    current_word_count = word_count
                    page_start_idx = line_idx
                else:
                    current_page.append(line)
                    current_word_count += word_count
            current_line_idx += 1

        if current_page:
            self.pages.append(" ".join(current_page))
            self.page_first_line_idxs.append(page_start_idx)
            for prev_line in range(page_start_idx, current_line_idx):
                self.line_to_page_index[prev_line] = len(self.pages) - 1

    def page_for_line(self, line):
        return self.line_to_page_index.get(line, 0)
        
    def get_start_line_for_page(self, page_idx):
        if 0 <= page_idx < len(self.page_first_line_idxs):
            return self.page_first_line_idxs[page_idx]
        return 0

    def get_page_number(self, page_idx):
        if self.is_quran:
            return str(page_idx + 1)
        start_line = page_idx * PAGE_LINES
        return self.line_to_page.get(start_line, "N/A")

    def get_surah_for_line(self, line):
        found_surah = ""
        for name, start, level in self.sections:
            if line >= start:
                found_surah = f"سورة {name}"
            else:
                break 
        return found_surah

class Book:
    """يمثل الكتاب بالكامل، يحتوي على أجزاء متعددة"""
    def __init__(self, path_or_dir):
        self.meta = {}
        self.author = ""
        self.title = ""
        
        if os.path.isdir(path_or_dir):
            self.dir = path_or_dir
            self.load_metadata() 
            self.parts = []
            for f in sorted(os.listdir(path_or_dir)):
                if f.lower().endswith((".html", ".htm", ".xhtml")):
                    self.parts.append(BookPart(os.path.join(path_or_dir, f)))
        else:
            self.dir = os.path.dirname(path_or_dir)
            self.load_metadata()
            self.parts = [BookPart(path_or_dir)]
        
        self.current_part_index = 0
        self.current_page_index = 0

    def load_metadata(self):
        """قراءة ملف meta.json وتحديد العنوان والمؤلف"""
        meta_path = os.path.join(self.dir, "meta.json")
        self.title = os.path.basename(self.dir).replace("_", " ")
        self.author = "" 
        
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.meta = json.load(f)
                    if "title" in self.meta:
                        self.title = self.meta["title"]
                    if "author" in self.meta:
                        if isinstance(self.meta["author"], dict):
                            self.author = self.meta["author"].get("name", "")
                        else:
                            self.author = str(self.meta["author"])
            except Exception as e:
                print(f"خطأ في قراءة الميتا: {e}")

    @property
    def current_part(self):
        return self.parts[self.current_part_index]

    @property
    def current_page(self):
        return self.current_part.pages[self.current_page_index]

    def goto_page(self, part_idx, page_idx):
        if 0 <= part_idx < len(self.parts):
            self.current_part_index = part_idx
            part = self.parts[part_idx]
            self.current_page_index = max(0, min(page_idx, len(part.pages)-1))

    def next_page(self):
        if self.current_page_index + 1 < len(self.current_part.pages):
            self.current_page_index += 1
        else:
            if self.current_part_index + 1 < len(self.parts):
                self.current_part_index += 1
                self.current_page_index = 0

    def prev_page(self):
        if self.current_page_index > 0:
            self.current_page_index -= 1
        else:
            if self.current_part_index > 0:
                self.current_part_index -= 1
                self.current_page_index = len(self.current_part.pages) - 1

    def total_pages(self):
        return sum(len(p.pages) for p in self.parts)

def find_line_matching_words(lines, words, remove_diac=None):
    if not words:
        return 0
    words_no_diac = [remove_diac(w).lower() for w in words] if remove_diac else [w.lower() for w in words]
    for i, l in enumerate(lines):
        l_no = remove_diac(l).lower() if remove_diac else l.lower()
        if all(w in l_no for w in words_no_diac):
            return i
    return 0
