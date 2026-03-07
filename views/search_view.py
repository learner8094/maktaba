# views/search_view.py
import os
import re
import threading
from typing import List, Tuple
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, Gdk, GLib

from book import Book
from config import BOOKS_DIR, load_config, save_config
from services.indexing import run_recollindex
from services.search import recoll_search, SearchHit

class SearchView(Gtk.Box):
    def __init__(self, open_cb):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_direction(Gtk.TextDirection.RTL)
        self.open_cb = open_cb

        self.cfg = load_config()
        self.cfg.setdefault("search", {})
        self._search_serial = 0

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

        self.match_combo = Gtk.ComboBoxText()
        self.match_combo.append("and", "AND")
        self.match_combo.append("or", "OR")
        self.match_combo.set_tooltip_text("AND: كل الكلمات، OR: أي كلمة")
        self.match_combo.set_active_id(self.cfg["search"].get("match_mode", "and"))
        bar.append(self.match_combo)

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

        self.section_combo = Gtk.ComboBoxText()
        self.section_combo.set_visible(False)
        bar.append(self.section_combo)

        btn_search = Gtk.Button(label="بحث")
        btn_search.add_css_class("suggested-action")
        btn_search.connect("clicked", self.perform_search)
        bar.append(btn_search)

        self.btn_reindex = Gtk.Button(label="فهرسة Recoll")
        self.btn_reindex.set_tooltip_text("فهرسة الكتب الجديدة عبر recollindex")
        self.btn_reindex.connect("clicked", self.on_reindex_clicked)
        bar.append(self.btn_reindex)

        btn_copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        btn_copy.set_tooltip_text("نسخ المقتطف المحدد")
        btn_copy.connect("clicked", self.copy_selected_snippet)
        bar.append(btn_copy)

        self.lbl_status = Gtk.Label(label="")
        self.lbl_status.set_halign(Gtk.Align.END)
        self.lbl_status.add_css_class("dim-label")
        self.append(self.lbl_status)

        # قائمة النتائج
        self.store = Gtk.ListStore(str, int, str, str, str, int)  # filepath, line, display, snippet, part_title, page_1based
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

        # العمود: الفصل
        col_part = Gtk.TreeViewColumn("الفصل")
        rend_part = Gtk.CellRendererText()
        rend_part.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_part.pack_start(rend_part, True)
        col_part.add_attribute(rend_part, "text", 4)
        col_part.set_fixed_width(220)
        self.tree.append_column(col_part)

        # العمود: الصفحة
        col_page = Gtk.TreeViewColumn("الصفحة")
        rend_page = Gtk.CellRendererText()
        col_page.pack_start(rend_page, True)
        col_page.add_attribute(rend_page, "text", 5)
        col_page.set_fixed_width(90)
        self.tree.append_column(col_page)

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
        self._populate_sections()
        if last_scope == "قسم معين" and last_scope_val:
            self.section_combo.set_active_id(last_scope_val)
        self.on_scope_changed(self.scope_combo)

    def _populate_sections(self):
        self.section_combo.remove_all()
        sections = []
        try:
            with os.scandir(BOOKS_DIR) as it:
                for entry in it:
                    if entry.is_dir():
                        sections.append(entry.name)
        except Exception:
            sections = []

        for section in sorted(sections):
            self.section_combo.append(section, section)

        if sections:
            self.section_combo.set_active(0)

    def on_scope_changed(self, combo):
        scope = combo.get_active_text()
        self.scope_entry.set_visible(scope == "كتاب واحد")
        self.section_combo.set_visible(scope == "قسم معين")

    def render_number(self, col, cell, model, iter_, data):
        path = model.get_path(iter_)
        cell.set_property("text", str(path.get_indices()[0] + 1))

    def _save_search_state(self):
        self.cfg.setdefault("search", {})
        self.cfg["search"]["last_query"] = self.entry.get_text().strip()
        self.cfg["search"]["last_scope"] = self.scope_combo.get_active_text()
        scope = self.scope_combo.get_active_text()
        if scope == "قسم معين":
            scope_value = self.section_combo.get_active_id() or ""
        else:
            scope_value = self.scope_entry.get_text().strip()
        self.cfg["search"]["last_scope_value"] = scope_value
        self.cfg["search"]["match_mode"] = self.match_combo.get_active_id() or "and"
        save_config(self.cfg)

    def perform_search(self, *args):
        query = self.entry.get_text().strip()
        if not query:
            return

        self._search_serial += 1
        search_serial = self._search_serial
        self.store.clear()
        self.lbl_status.set_label("جاري البحث...")
        self.entry.set_sensitive(False)
        self.match_combo.set_sensitive(False)
        self.scope_combo.set_sensitive(False)
        self.scope_entry.set_sensitive(False)
        self.section_combo.set_sensitive(False)

        scope = self.scope_combo.get_active_text()
        if scope == "قسم معين":
            scope_value = self.section_combo.get_active_id() or ""
        else:
            scope_value = self.scope_entry.get_text().strip()

        match_mode = self.match_combo.get_active_id() or "and"
        self._save_search_state()

        def worker():
            rows: List[Tuple[str, int, str, str, str, int]] = []
            try:
                hits = recoll_search(query, scope=scope, scope_value=scope_value, limit=200, match_mode=match_mode)
                books_cache = {}
                for h in hits:
                    book_dir = os.path.dirname(h.filepath)
                    part_title = "-"
                    page_idx_1based = 1
                    try:
                        if book_dir not in books_cache:
                            books_cache[book_dir] = Book(book_dir)
                        book = books_cache[book_dir]
                        hit_path = os.path.normpath(os.path.realpath(h.filepath))
                        for part in book.parts:
                            part_path = os.path.normpath(os.path.realpath(part.path))
                            if part_path != hit_path:
                                continue

                            target_line = max(0, h.line_num_1based - 1)
                            page_idx_1based = part.page_for_line(target_line) + 1

                            # استخرج عنوان الفصل الأقرب قبل السطر المطابق
                            nearest_section = None
                            for sec_title, sec_line, _sec_level in part.sections:
                                if sec_line <= target_line:
                                    nearest_section = sec_title
                                else:
                                    break

                            if nearest_section:
                                part_title = nearest_section
                            else:
                                part_title = os.path.splitext(os.path.basename(part.path))[0]
                            break
                    except Exception:
                        pass
                    rows.append((h.filepath, h.line_num_1based, h.display, h.snippet, part_title, page_idx_1based))
            except Exception as e:
                GLib.idle_add(self._finish_search, search_serial, [], f"فشل البحث: {e}")
                return

            GLib.idle_add(self._finish_search, search_serial, rows, None)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_search(self, search_serial: int, rows: List[Tuple[str, int, str, str, str, int]], error_msg: str | None):
        if search_serial != self._search_serial:
            return False

        self.entry.set_sensitive(True)
        self.match_combo.set_sensitive(True)
        self.scope_combo.set_sensitive(True)
        self.scope_entry.set_sensitive(True)
        self.section_combo.set_sensitive(True)

        if error_msg:
            self.lbl_status.set_label(error_msg)
            return False

        for row in rows:
            self.store.append(list(row))

        self.lbl_status.set_label(f"النتائج: {len(rows)}")
        return False

    def copy_selected_snippet(self, *args):
        sel = self.tree.get_selection()
        model, it = sel.get_selected()
        if not it:
            return
        snippet = model.get_value(it, 3) or ""
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(snippet)

    def on_reindex_clicked(self, _btn):
        self.btn_reindex.set_sensitive(False)
        self.lbl_status.set_label("جاري فهرسة الكتب عبر Recoll...")

        def worker():
            ok, err = run_recollindex()
            if ok:
                GLib.idle_add(self._finish_reindex, "اكتملت فهرسة Recoll بنجاح.")
                return
            GLib.idle_add(self._finish_reindex, f"فشلت فهرسة Recoll: {err}")

        threading.Thread(target=worker, daemon=True).start()

    def _finish_reindex(self, message: str):
        self.btn_reindex.set_sensitive(True)
        self.lbl_status.set_label(message)
        return False

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
            target_path = os.path.normpath(os.path.realpath(filepath))
            part_idx = next(i for i, p in enumerate(book.parts) if os.path.normpath(os.path.realpath(p.path)) == target_path)
            page_idx = book.parts[part_idx].page_for_line(line_num - 1)
            words = [w for w in re.split(r"\s+", self.entry.get_text().strip()) if w and w.lower() not in {"and", "or"}]
            self.open_cb(book, part_idx, page_idx, words, line_num - 1)
        except Exception as e:
            print(f"فشل في فتح النتيجة: {e}")

    def select_adjacent_result(self, step: int):
        if not step or len(self.store) == 0:
            return

        selection = self.tree.get_selection()
        model, current_iter = selection.get_selected()

        if current_iter:
            path = model.get_path(current_iter)
            current_index = path.get_indices()[0]
        else:
            current_index = -1 if step > 0 else len(self.store)

        next_index = max(0, min(len(self.store) - 1, current_index + step))
        path = Gtk.TreePath.new_from_indices([next_index])

        selection.select_path(path)
        self.tree.set_cursor(path, None, False)
        self.tree.scroll_to_cell(path, None, False, 0.0, 0.0)

    def focus_search_entry(self):
        self.entry.grab_focus()
        self.entry.select_region(0, -1)
