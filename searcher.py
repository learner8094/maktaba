#!/usr/bin/env python3
import gi
import os
import subprocess
import re
import json
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Pango, GLib

BASE_DIR = os.path.dirname(__file__)
BOOKS_DIR = os.path.join(BASE_DIR, "books")
RECOLL_DIR = os.path.join(BASE_DIR, ".recoll")
CONFIG_PATH = os.path.expanduser("~/.config/recoll-gtk/config.json")
PAGE_LINES = 40

# ================= CONFIG =================
def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_config(config):
    Path(CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

CONFIG = load_config()

# ================= HTML PARSER =================
class HTMLExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines = []
        self.sections = []
        self._line = 0
        self._in_h = False

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3"):
            self._in_h = True

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3"):
            self._in_h = False

    def handle_data(self, data):
        t = data.strip()
        if not t:
            return
        if self._in_h:
            self.sections.append((t, self._line))
        self.lines.append(t)
        self._line += 1

# ================= BOOK MODEL =================
class Book:
    def __init__(self, path):
        self.path = path
        self.section = os.path.basename(os.path.dirname(path))
        self.title = os.path.splitext(os.path.basename(path))[0]
        self.lines = []
        self.sections = []
        self.pages = []
        self.load()

    def load(self):
        with open(self.path, encoding="utf-8", errors="ignore") as f:
            html = f.read()
        p = HTMLExtractor()
        p.feed(html)
        self.lines = p.lines
        self.sections = p.sections
        self.paginate()

    def paginate(self):
        self.pages.clear()
        for i in range(0, len(self.lines), PAGE_LINES):
            self.pages.append("\n".join(self.lines[i:i+PAGE_LINES]))

    def page_for_line(self, line):
        return min(line // PAGE_LINES, len(self.pages)-1)

# ================= READER VIEW =================
class ReaderView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.book = None
        self.page = 0
        self.font_size = CONFIG.get("font_size", 18)
        self.highlight_tag = None

        # قائمة الفصول
        self.section_store = Gtk.ListStore(str, int)
        self.section_view = Gtk.TreeView(model=self.section_store)
        self.section_view.append_column(Gtk.TreeViewColumn("الفصول", Gtk.CellRendererText(), text=0))
        self.section_view.get_selection().connect("changed", self.on_section_selected)
        sec_scroll = Gtk.ScrolledWindow()
        sec_scroll.set_size_request(260, -1)
        sec_scroll.set_child(self.section_view)
        self.append(sec_scroll)

        # الجانب الأيمن: أزرار + النص
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(right)

        # أزرار التحكم
        bar = Gtk.Box(spacing=6)
        right.append(bar)
        for label, cb in [
            ("⏮", lambda: self.goto_page(0)),
            ("◀", lambda: self.goto_page(self.page-1)),
            ("▶", lambda: self.goto_page(self.page+1)),
            ("⏭", lambda: self.goto_page(len(self.book.pages)-1 if self.book else 0)),
            ("أ-", lambda: self.change_font(-2)),
            ("أ+", lambda: self.change_font(+2))
        ]:
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda w, f=cb: f())
            bar.append(b)

        # TextView
        self.text = Gtk.TextView()
        self.text.set_editable(False)
        self.text.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text.set_hexpand(True)
        self.text.set_vexpand(True)
        self.buffer = self.text.get_buffer()
        self.highlight_tag = self.buffer.create_tag("highlight", background="yellow", foreground="black")

        self.css_provider = Gtk.CssProvider()
        self.apply_font()
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.text)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        right.append(scroll)

    def apply_font(self):
        css = f"textview {{ font-size: {self.font_size}px; }}"
        self.css_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def change_font(self, delta):
        self.font_size = max(12, min(36, self.font_size + delta))
        CONFIG["font_size"] = self.font_size
        save_config(CONFIG)
        self.apply_font()

    def load_book(self, book, page=0, highlight_words=None):
        self.book = book
        self.page = page
        self.section_store.clear()
        for title, line in book.sections:
            self.section_store.append([title, line])
        self.render(highlight_words)

    def render(self, highlight_words=None):
        if not self.book:
            self.buffer.set_text("")
            return
        text = self.book.pages[self.page]
        self.buffer.set_text(text)
        self.buffer.remove_tag(self.highlight_tag, self.buffer.get_start_iter(), self.buffer.get_end_iter())
        if highlight_words:
            for word in highlight_words:
                start_iter = self.buffer.get_start_iter()
                while True:
                    match = start_iter.forward_search(word, Gtk.TextSearchFlags.CASE_INSENSITIVE, None)
                    if not match:
                        break
                    match_start, match_end = match
                    self.buffer.apply_tag(self.highlight_tag, match_start, match_end)
                    start_iter = match_end

    def goto_page(self, page):
        if self.book and 0 <= page < len(self.book.pages):
            self.page = page
            CONFIG.setdefault("last_positions", {})[self.book.path] = {"page": page}
            save_config(CONFIG)
            self.render()

    def on_section_selected(self, selection):
        model, iter_ = selection.get_selected()
        if iter_:
            line = model.get_value(iter_, 1)
            self.goto_page(self.book.page_for_line(line))

# ================= LIBRARY VIEW =================
class LibraryView(Gtk.TreeView):
    def __init__(self, open_cb):
        self.store = Gtk.TreeStore(str, str)
        super().__init__(model=self.store)
        self.open_cb = open_cb
        self.append_column(Gtk.TreeViewColumn("المكتبة", Gtk.CellRendererText(), text=0))
        self.load_books()
        self.connect("row-activated", self.on_row_activated)

    def load_books(self):
        self.store.clear()
        if not os.path.isdir(BOOKS_DIR):
            return
        for section in sorted(os.listdir(BOOKS_DIR)):
            sec_path = os.path.join(BOOKS_DIR, section)
            if not os.path.isdir(sec_path):
                continue
            sec_iter = self.store.append(None, [section, None])
            for f in sorted(os.listdir(sec_path)):
                if f.endswith(".html"):
                    self.store.append(sec_iter, [os.path.splitext(f)[0], os.path.join(sec_path, f)])

    def on_row_activated(self, view, path, col):
        iter_ = self.store.get_iter(path)
        filepath = self.store.get_value(iter_, 1)
        if filepath:
            self.open_cb(filepath)

# ================= SEARCH VIEW =================
class SearchView(Gtk.Box):
    def __init__(self, open_cb):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.open_cb = open_cb

        bar = Gtk.Box(spacing=6)
        self.append(bar)
        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("ابحث في الكتب...")
        self.entry.connect("activate", self.perform_search)
        bar.append(self.entry)

        # نطاق البحث
        self.scope_combo = Gtk.ComboBoxText()
        self.scope_combo.append_text("كل الكتب")
        for section in sorted(os.listdir(BOOKS_DIR)):
            sec_path = os.path.join(BOOKS_DIR, section)
            if os.path.isdir(sec_path):
                self.scope_combo.append_text(section)
        self.scope_combo.set_active(0)
        bar.append(self.scope_combo)

        btn = Gtk.Button(label="بحث")
        btn.connect("clicked", self.perform_search)
        bar.append(btn)

        self.store = Gtk.ListStore(str, str, str, str, str)
        self.tree = Gtk.TreeView(model=self.store)

        col_num = Gtk.TreeViewColumn("رقم")
        rend_num = Gtk.CellRendererText()
        col_num.pack_start(rend_num, True)
        col_num.set_cell_data_func(rend_num, self.render_number)
        col_num.set_fixed_width(60)
        self.tree.append_column(col_num)

        col_book = Gtk.TreeViewColumn("الكتاب")
        rend_book = Gtk.CellRendererText()
        rend_book.props.weight = 700
        col_book.pack_start(rend_book, True)
        col_book.add_attribute(rend_book, "text", 2)
        col_book.set_fixed_width(450)
        col_book.set_resizable(True)
        self.tree.append_column(col_book)

        col_snip = Gtk.TreeViewColumn("المقتطف")
        rend_snip = Gtk.CellRendererText()
        rend_snip.props.ellipsize = Pango.EllipsizeMode.END
        col_snip.pack_start(rend_snip, True)
        col_snip.add_attribute(rend_snip, "text", 3)
        col_snip.set_expand(True)
        self.tree.append_column(col_snip)

        self.tree.connect("row-activated", self.on_row_activated)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.tree)
        scroll.set_vexpand(True)
        self.append(scroll)

    def render_number(self, col, cell, model, iter_, data):
        path = model.get_path(iter_)
        cell.set_property("text", str(path[0]+1))

    def perform_search(self, *args):
        query = self.entry.get_text().strip()
        if not query:
            return
        self.store.clear()

        # تحديد نطاق البحث
        scope = self.scope_combo.get_active_text()
        cmd = ["recollq", "-c", RECOLL_DIR, "-A", "-g", "50", query]
        if scope != "كل الكتب":
            # البحث في مسار محدد
            scope_path = os.path.join(BOOKS_DIR, scope)
            cmd = ["recollq", "-c", RECOLL_DIR, "-A", "-g", "50", "-b", scope_path, query]

        try:
            out = subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()
        except Exception:
            return

        current_file = None
        in_snip = False
        for line in out:
            if "[file://" in line and "bytes" in line:
                m = re.search(r'\[(file://[^]]+)\]', line)
                if m:
                    current_file = m.group(1).replace("file://", "")
                in_snip = False
                continue
            if line.strip() == "SNIPPETS":
                in_snip = True
                continue
            if line.strip() == "/SNIPPETS":
                in_snip = False
                continue
            if in_snip and re.match(r'^\d+ : ', line):
                ln, txt = line.split(" : ", 1)
                section = os.path.basename(os.path.dirname(current_file))
                title = os.path.splitext(os.path.basename(current_file))[0]
                display = f"{section} | {title}"
                short = txt[:180] + "..." if len(txt) > 180 else txt
                self.store.append([current_file, txt, display, short, ln])

    def on_row_activated(self, tree, path, col):
        model = tree.get_model()
        iter_ = model.get_iter(path)
        if iter_:
            filepath = model.get_value(iter_, 0)
            line_num = int(model.get_value(iter_, 4))
            book = Book(filepath)
            page = book.page_for_line(line_num)
            query_text = self.entry.get_text().strip()
            highlight_words = query_text.split() if query_text else []
            self.open_cb(book, page, highlight_words)

# ================= MAIN APPLICATION =================
class MainApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.zam.maktaba")

    def do_startup(self):
        Gtk.Application.do_startup(self)
        # Keyboard shortcuts
        self.add_accelerator("<Control>f", None, 0, 0, 0)  # Ctrl+F -> البحث
        self.add_accelerator("<Control>plus", None, 0, 0, 0)  # Ctrl++ -> تكبير
        self.add_accelerator("<Control>minus", None, 0, 0, 0)  # Ctrl+- -> تصغير

    def do_activate(self):
        # Auto-indexing: تحديث Recoll عند أي تغيير
        self.check_and_index()

        win = Gtk.ApplicationWindow(application=self)
        win.set_default_size(1500, 900)

        notebook = Gtk.Notebook()
        win.set_child(notebook)

        # لسان القراءة
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        library = LibraryView(self.open_book)
        self.reader = ReaderView()
        paned.set_start_child(library)
        paned.set_end_child(self.reader)
        notebook.append_page(paned, Gtk.Label(label="📖 القراءة"))

        # لسان البحث
        self.search = SearchView(self.open_from_search)
        notebook.append_page(self.search, Gtk.Label(label="🔍 البحث"))

        self.notebook = notebook
        win.present()

    def open_book(self, filepath):
        book = Book(filepath)
        # استرجاع آخر صفحة
        last_pos = CONFIG.get("last_positions", {}).get(filepath, {})
        page = last_pos.get("page", 0)
        self.reader.load_book(book, page)

    def open_from_search(self, book, page, highlight_words=None):
        self.reader.load_book(book, page, highlight_words)
        self.notebook.set_current_page(0)

    # ================= AUTO-INDEXING =================
    def check_and_index(self):
        index_file = os.path.join(RECOLL_DIR, "recoll.idx")
        need_index = False
        if not os.path.exists(index_file):
            need_index = True
        else:
            idx_time = os.path.getmtime(index_file)
            for root, dirs, files in os.walk(BOOKS_DIR):
                for f in files:
                    if f.endswith(".html"):
                        path = os.path.join(root, f)
                        if os.path.getmtime(path) > idx_time:
                            need_index = True
                            break
        if need_index:
            cmd = ["recollindex", "-c", RECOLL_DIR]
            subprocess.run(cmd)

def main():
    MainApp().run(None)

if __name__ == "__main__":
    main()

