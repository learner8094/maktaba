# views/quran_view.py
import os
import re
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, Gdk, GLib
from typing import Optional, List

from book import Book
from config import BOOKS_DIR, load_config, save_config

QURAN_FILE = os.path.join(BOOKS_DIR, "quran.xhtml")
CONFIG = load_config()

class QuranView(Gtk.Box):
    def __init__(self, open_cb=None, save_cb=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        self.font_size = CONFIG.get("quran_font_size", 22)
        self.highlight_words: Optional[List[str]] = None
        self.attribution_enabled = False
        self.book: Optional[Book] = None

        # 1. قائمة السور الجانبية
        self.surah_store = Gtk.ListStore(str, int)
        self.surah_view = Gtk.TreeView(model=self.surah_store)
        self.surah_view.set_headers_visible(False)
        
        rend = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn("السورة", rend, text=0)
        self.surah_view.append_column(col)
        self.surah_view.connect("row-activated", self.on_surah_activated)
        
        scroll_sura = Gtk.ScrolledWindow()
        scroll_sura.set_size_request(180, -1)
        scroll_sura.set_child(self.surah_view)
        self.append(scroll_sura)

        # 2. المنطقة الرئيسية
        main_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_area.set_hexpand(True)
        self.append(main_area)

        # شريط الأدوات
        toolbar = Gtk.Box(spacing=8)
        main_area.append(toolbar)
        
        nav_btns = [
            ("⏭", self.goto_first),
            ("▶", self.prev_pg),
            ("◀", self.next_pg),
            ("⏮", self.goto_last)
        ]
        
        for label, cmd in nav_btns:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", lambda x, c=cmd: c())
            toolbar.append(btn)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        btn_in = Gtk.Button(label="أ+")
        btn_in.connect("clicked", self.zoom_in)
        toolbar.append(btn_in)
        btn_out = Gtk.Button(label="أ-")
        btn_out.connect("clicked", self.zoom_out)
        toolbar.append(btn_out)

        self.check_attr = Gtk.CheckButton(label="عزو")
        self.check_attr.connect("toggled", lambda b: setattr(self, 'attribution_enabled', b.get_active()))
        toolbar.append(self.check_attr)

        # الفاصل المتحرك (Paned) - يقسم الشاشة أفقياً إلى نص (أعلى) وبحث (أسفل)
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.paned.set_vexpand(True) # الفاصل نفسه يتمدد
        main_area.append(self.paned)

        # الجزء العلوي: نص القرآن
        self.text = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD)
        self.text.add_css_class("quran-text")
        
        self.buffer = self.text.get_buffer()
        self.text.connect("copy-clipboard", self.on_copy)
        
        self.tag_hl = self.buffer.create_tag("hl", background="#dae3f3") 
        self.tag_bold = self.buffer.create_tag("bold", weight=Pango.Weight.BOLD)

        scroll_txt = Gtk.ScrolledWindow()
        scroll_txt.set_child(self.text)
        scroll_txt.set_vexpand(True) # السماح لنص القرآن بالتمدد أيضاً
        scroll_txt.set_hexpand(True)
        self.paned.set_start_child(scroll_txt)
        self.paned.set_resize_start_child(True)

        # الجزء السفلي: البحث
        search_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        # شريط البحث
        search_bar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("ابحث في القرآن...")
        self.entry.set_hexpand(True) # تمديد حقل الإدخال
        self.entry.connect("activate", self.do_search)
        
        btn_search = Gtk.Button(label="بحث")
        btn_search.connect("clicked", self.do_search)
        
        search_bar_box.append(self.entry)
        search_bar_box.append(btn_search)
        search_section.append(search_bar_box)

        # جدول النتائج
        self.res_store = Gtk.ListStore(str, int, str, str, str)
        self.res_view = Gtk.TreeView(model=self.res_store)
        
        cols_info = [("السورة", 2, 130), ("الآية", 3, 70), ("نص الآية", 4, -1)]
        for title, col_idx, width in cols_info:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=col_idx)
            if width > 0: column.set_fixed_width(width)
            if col_idx == 4: 
                column.set_expand(True)
                renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            self.res_view.append_column(column)

        self.res_view.connect("row-activated", self.on_res_click)
        
        scroll_res = Gtk.ScrolledWindow()
        scroll_res.set_child(self.res_view)
        
        # === الإصلاح هنا ===
        # إجبار حاوية النتائج على التمدد عمودياً وأفقياً لملء المساحة المتبقية
        scroll_res.set_vexpand(True) 
        scroll_res.set_hexpand(True)
        
        search_section.append(scroll_res)

        self.paned.set_end_child(search_section)
        self.paned.set_resize_end_child(True)
        self.paned.set_position(450) # الحجم المبدئي للجزء العلوي

        # مزود CSS لحجم الخط المتغير
        self.font_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), 
            self.font_provider, 
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.apply_font_size()
        
        self.load_book()

    def apply_font_size(self):
        css = f".quran-text {{ font-size: {self.font_size}pt; }}"
        self.font_provider.load_from_data(css.encode())

    def render(self, words: Optional[List[str]] = None):
        if words: self.highlight_words = words
        self.buffer.set_text(self.book.current_page)
        
        txt = self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False)
        # البحث عن عناوين السور وتغليظها
        for name, _, _ in self.book.current_part.sections:
            title = f"سورة {name}"
            start_search = self.buffer.get_start_iter()
            while True:
                res = start_search.forward_search(title, 0, self.buffer.get_end_iter())
                if not res: break
                s, e = res
                self.buffer.apply_tag(self.tag_bold, s, e)
                start_search = e

        if self.highlight_words:
            for w in self.highlight_words:
                pat = "[\u064B-\u0652\u0670\u06D6-\u06ED\u0640]*".join(list(re.escape(w)))
                for m in re.finditer(pat, txt):
                    self.buffer.apply_tag(self.tag_hl, self.buffer.get_iter_at_offset(m.start()), self.buffer.get_iter_at_offset(m.end()))
        
        self.text.scroll_to_iter(self.buffer.get_start_iter(), 0, False, 0, 0)

    def on_copy(self, tv):
        bound = self.buffer.get_selection_bounds()
        if not bound: return False
        start, end = bound
        if not start.starts_word(): start.backward_word_start()
        if not end.ends_word(): end.forward_word_end()
        self.buffer.select_range(start, end)
        sel = self.buffer.get_text(start, end, False).strip()
        if self.attribution_enabled:
            real_line = self.book.current_part.get_start_line_for_page(self.book.current_page_index) + start.get_line()
            surah = self.book.current_part.get_surah_for_line(real_line)
            modified = f"«{sel}» [{surah}]"
        else:
            modified = sel
        GLib.timeout_add(100, self._set_clip, modified)
        return True

    def _set_clip(self, txt: str):
        Gdk.Display.get_default().get_clipboard().set(txt)
        return False

    def zoom_in(self, *a):
        self.font_size += 2
        self.apply_font_size(); self.save_cfg()

    def zoom_out(self, *a):
        if self.font_size > 8:
            self.font_size -= 2
            self.apply_font_size(); self.save_cfg()

    def save_cfg(self):
        CONFIG["quran_font_size"] = self.font_size
        save_config(CONFIG)

    def load_book(self):
        if os.path.exists(QURAN_FILE):
            self.book = Book(QURAN_FILE)
            self.surah_store.clear()
            for name, line, level in self.book.current_part.sections:
                self.surah_store.append([f"سورة {name}", line])
            self.render()

    def remove_diacritics(self, text: str) -> str:
        return ''.join(c for c in text if c not in "ًٌٍَُِّْ")

    def do_search(self, *a):
        q = self.entry.get_text().strip()
        self.res_store.clear()
        if not q: return
        search_q = self.remove_diacritics(q)
        for idx, line in enumerate(self.book.current_part.lines):
            if search_q in self.remove_diacritics(line):
                sura = self.book.current_part.get_surah_for_line(idx)
                match = re.search(r'\((\d+)\)$', line)
                aya_num = match.group(1) if match else "-"
                self.res_store.append([QURAN_FILE, idx, sura, aya_num, line])

    def on_res_click(self, t, p, c):
        self.highlight_words = self.entry.get_text().split()
        line_idx = self.res_store[p][1]
        self.book.goto_page(0, self.book.current_part.page_for_line(line_idx))
        self.render()

    def next_pg(self):
        if not self.book:
            return
        self.book.next_page()
        self.render()

    def prev_pg(self):
        if not self.book:
            return
        self.book.prev_page()
        self.render()

    def goto_first(self):
        if not self.book:
            return
        self.book.goto_page(0, 0)
        self.render()

    def goto_last(self):
        if not self.book:
            return
        self.book.goto_page(0, len(self.book.current_part.pages) - 1)
        self.render()
    
    def on_surah_activated(self, t, p, c):
        line = self.surah_store[p][1]
        self.book.goto_page(0, self.book.current_part.page_for_line(line))
        self.render()

    def load_book_object(self, book: Book, page: int, words: Optional[List[str]]=None):
        self.book = book
        self.book.current_page_index = page
        self.render(words)
