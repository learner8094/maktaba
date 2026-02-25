# views/search_view.py
import os
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, Gdk

from book import Book
from config import load_config, save_config
from services.search import recoll_search, SearchHit

class SearchView(Gtk.Box):
    def __init__(self, open_cb):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_direction(Gtk.TextDirection.RTL)
        self.open_cb = open_cb

        self.cfg = load_config()
        self.cfg.setdefault("search", {})

        # شريط البحث
        bar = Gtk.Box(spacing=8)
        bar.set_halign(Gtk.Align.END)
        bar.add_css_class("toolbar")
        self.append(bar)

        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("ابحث في الكتب...")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self.perform_search)
        bar.append(self.entry)

        self.scope_combo = Gtk.ComboBoxText()
        self.scope_combo.append_text("كل الكتب")
        self.scope_combo.append_text("قسم معين")
        self.scope_combo.append_text("كتاب واحد")
        self.scope_combo.connect("changed", self.on_scope_changed)
        bar.append(self.scope_combo)

        self.scope_entry = Gtk.Entry()
        self.scope_entry.set_placeholder_text("اسم القسم أو الكتاب")
        self.scope_entry.set_visible(False)
        bar.append(self.scope_entry)

        btn_search = Gtk.Button(label="بحث")
        btn_search.add_css_class("suggested-action")
        btn_search.connect("clicked", self.perform_search)
        bar.append(btn_search)

        btn_copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        btn_copy.set_tooltip_text("نسخ المقتطف المحدد")
        btn_copy.connect("clicked", self.copy_selected_snippet)
        bar.append(btn_copy)

        self.lbl_status = Gtk.Label(label="")
        self.lbl_status.set_halign(Gtk.Align.END)
        self.lbl_status.add_css_class("dim-label")
        self.append(self.lbl_status)

        # قائمة النتائج
        self.store = Gtk.ListStore(str, int, str, str)  # filepath, line, display, snippet
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_direction(Gtk.TextDirection.RTL)

        # العمود: رقم
        col_num = Gtk.TreeViewColumn("رقم")
        rend_num = Gtk.CellRendererText()
        col_num.pack_start(rend_num, True)
        col_num.set_cell_data_func(rend_num, self.render_number)
        col_num.set_fixed_width(70)
        self.tree.append_column(col_num)

        # العمود: القسم | الكتاب
        col_book = Gtk.TreeViewColumn("الكتاب")
        rend_book = Gtk.CellRendererText(weight=700)
        rend_book.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_book.pack_start(rend_book, True)
        col_book.add_attribute(rend_book, "text", 2)
        col_book.set_fixed_width(420)
        self.tree.append_column(col_book)

        # العمود: مقتطف
        col_snip = Gtk.TreeViewColumn("المقتطف")
        rend_snip = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        col_snip.pack_start(rend_snip, True)
        col_snip.add_attribute(rend_snip, "text", 3)
        col_snip.set_expand(True)
        self.tree.append_column(col_snip)

        self.tree.connect("row-activated", self.on_row_activated)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.tree)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        self.append(scroll)

        # استرجاع آخر إعدادات
        last_q = self.cfg["search"].get("last_query", "")
        last_scope = self.cfg["search"].get("last_scope", "كل الكتب")
        last_scope_val = self.cfg["search"].get("last_scope_value", "")

        self.entry.set_text(last_q)
        self.scope_combo.set_active({"كل الكتب":0,"قسم معين":1,"كتاب واحد":2}.get(last_scope, 0))
        self.scope_entry.set_text(last_scope_val)
        self.on_scope_changed(self.scope_combo)

    def on_scope_changed(self, combo):
        self.scope_entry.set_visible(combo.get_active_text() != "كل الكتب")

    def render_number(self, col, cell, model, iter_, data):
        path = model.get_path(iter_)
        cell.set_property("text", str(path.get_indices()[0] + 1))

    def _save_search_state(self):
        self.cfg.setdefault("search", {})
        self.cfg["search"]["last_query"] = self.entry.get_text().strip()
        self.cfg["search"]["last_scope"] = self.scope_combo.get_active_text()
        self.cfg["search"]["last_scope_value"] = self.scope_entry.get_text().strip()
        save_config(self.cfg)

    def perform_search(self, *args):
        query = self.entry.get_text().strip()
        if not query:
            return
        self.store.clear()
        self.lbl_status.set_label("جاري البحث...")

        scope = self.scope_combo.get_active_text()
        scope_value = self.scope_entry.get_text().strip()

        hits = recoll_search(query, scope=scope, scope_value=scope_value, limit=200)
        for h in hits:
            self.store.append([h.filepath, h.line_num_1based, h.display, h.snippet])

        self.lbl_status.set_label(f"النتائج: {len(hits)}")
        self._save_search_state()

    def copy_selected_snippet(self, *args):
        sel = self.tree.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        snippet = model.get_value(it, 3) or ""
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(snippet)

    def on_row_activated(self, tree, path, col):
        model = tree.get_model()
        iter_ = model.get_iter(path)
        if not iter_:
            return
        filepath = model.get_value(iter_, 0)
        line_num = model.get_value(iter_, 1)

        book_dir = os.path.dirname(filepath)
        try:
            book = Book(book_dir)
            part_idx = next(i for i, p in enumerate(book.parts) if p.path == filepath)
            page_idx = book.parts[part_idx].page_for_line(line_num - 1)
            words = self.entry.get_text().strip().split()
            self.open_cb(book, part_idx, page_idx, words)
        except Exception as e:
            print(f"فشل في فتح النتيجة: {e}")
