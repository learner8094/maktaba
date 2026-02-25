# views/ai_view.py
import os
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Pango

import threading
from typing import List, Optional, Tuple

from book import Book
from config import BOOKS_DIR
from services.search import recoll_search
from services.semantic import SemanticIndex, EmbeddingBackend, SemanticResult

class AIView(Gtk.Box):
    """لسان البحث الدلالي (Semantic Search)"""
    def __init__(self, open_cb):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_direction(Gtk.TextDirection.RTL)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.set_margin_start(10)
        self.set_margin_end(10)

        self.open_cb = open_cb
        self.backend = EmbeddingBackend()
        self.index = SemanticIndex(self.backend)

        self._busy = False

        # شريط التحكم
        bar = Gtk.Box(spacing=8)
        bar.set_halign(Gtk.Align.END)
        bar.add_css_class("toolbar")
        self.append(bar)

        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("ابحث بالمعنى (مثال: حكم الصلاة في السفر)...")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self.on_search)
        bar.append(self.entry)

        self.mode_combo = Gtk.ComboBoxText()
        self.mode_combo.append_text("سريع: Recoll + ترتيب دلالي")
        self.mode_combo.append_text("كامل: فهرس دلالي")
        self.mode_combo.set_active(0)
        bar.append(self.mode_combo)

        self.scope_combo = Gtk.ComboBoxText()
        self.scope_combo.append_text("كل الكتب")
        self.scope_combo.append_text("قسم معين")
        self.scope_combo.append_text("كتاب واحد")
        self.scope_combo.set_active(0)
        self.scope_combo.connect("changed", self.on_scope_changed)
        bar.append(self.scope_combo)

        self.scope_entry = Gtk.Entry()
        self.scope_entry.set_placeholder_text("اسم القسم أو الكتاب")
        self.scope_entry.set_visible(False)
        bar.append(self.scope_entry)

        self.btn_search = Gtk.Button(label="بحث")
        self.btn_search.add_css_class("suggested-action")
        self.btn_search.connect("clicked", self.on_search)
        bar.append(self.btn_search)

        self.btn_index = Gtk.Button(label="فهرسة دلالية")
        self.btn_index.set_tooltip_text("يبني فهرسًا دلاليًا كاملًا (قد يأخذ وقتًا بحسب حجم مكتبتك)")
        self.btn_index.connect("clicked", self.on_build_index)
        bar.append(self.btn_index)

        # شريط الحالة
        self.status = Gtk.Label(label="")
        self.status.set_halign(Gtk.Align.END)
        self.status.add_css_class("dim-label")
        self.append(self.status)

        # ملاحظة الاعتماديات
        if not self.backend.available:
            self.status.set_label("للاستفادة من البحث الدلالي: ثبّت fastembed (مستحسن) أو sentence-transformers.")
        else:
            self.status.set_label(f"محرك التضمين: {self.backend.name}")

        # النتائج
        self.store = Gtk.ListStore(str, int, int, float, str, str)  
        # (book_dir, part_idx, page_idx, score, display, snippet)

        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(True)
        self.tree.set_direction(Gtk.TextDirection.RTL)
        self.tree.connect("row-activated", self.on_row_activated)

        # العمود: الترتيب
        col_num = Gtk.TreeViewColumn("رقم")
        rend_num = Gtk.CellRendererText()
        col_num.pack_start(rend_num, True)
        col_num.set_cell_data_func(rend_num, self.render_number)
        col_num.set_fixed_width(70)
        self.tree.append_column(col_num)

        # العمود: الدرجة
        col_score = Gtk.TreeViewColumn("الملاءمة")
        rend_score = Gtk.CellRendererText()
        col_score.pack_start(rend_score, True)
        col_score.set_cell_data_func(rend_score, self.render_score)
        col_score.set_fixed_width(90)
        self.tree.append_column(col_score)

        # العمود: الكتاب
        col_book = Gtk.TreeViewColumn("الكتاب")
        rend_book = Gtk.CellRendererText(weight=700)
        rend_book.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_book.pack_start(rend_book, True)
        col_book.add_attribute(rend_book, "text", 4)
        col_book.set_fixed_width(420)
        self.tree.append_column(col_book)

        # العمود: مقتطف
        col_snip = Gtk.TreeViewColumn("مقتطف")
        rend_snip = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        col_snip.pack_start(rend_snip, True)
        col_snip.add_attribute(rend_snip, "text", 5)
        col_snip.set_expand(True)
        self.tree.append_column(col_snip)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.tree)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        self.append(scroll)

    def on_scope_changed(self, combo):
        self.scope_entry.set_visible(combo.get_active_text() != "كل الكتب")

    def render_number(self, col, cell, model, iter_, data):
        path = model.get_path(iter_)
        cell.set_property("text", str(path.get_indices()[0] + 1))

    def render_score(self, col, cell, model, iter_, data):
        score = model.get_value(iter_, 3)
        try:
            cell.set_property("text", f"{float(score):.2f}")
        except Exception:
            cell.set_property("text", "")

    def _set_busy(self, busy: bool, text: str = ""):
        self._busy = busy
        self.btn_search.set_sensitive(not busy)
        self.btn_index.set_sensitive(not busy)
        if text:
            self.status.set_label(text)

    def on_search(self, *args):
        if self._busy:
            return
        query = self.entry.get_text().strip()
        if not query:
            return
        if not self.backend.available:
            self.status.set_label("البحث الدلالي غير متاح: ثبّت fastembed أو sentence-transformers.")
            return

        self.store.clear()
        self._set_busy(True, "جاري البحث...")

        mode = self.mode_combo.get_active_text()
        scope = self.scope_combo.get_active_text()
        scope_value = self.scope_entry.get_text().strip()

        th = threading.Thread(
            target=self._search_thread,
            args=(query, mode, scope, scope_value),
            daemon=True
        )
        th.start()

    def _search_thread(self, query: str, mode: str, scope: str, scope_value: str):
        try:
            if mode.startswith("سريع"):
                results = self._search_hybrid(query, scope, scope_value)
            else:
                results = self._search_full(query, scope, scope_value)

            GLib.idle_add(self._fill_results, results, query)
        except Exception as e:
            GLib.idle_add(self._set_busy, False, f"فشل البحث: {e}")

    def _search_full(self, query: str, scope: str, scope_value: str) -> List[Tuple[str,int,int,float,str,str]]:
        # بحث في الفهرس الدلالي الكامل
        book_dir_filter = None
        if scope == "كتاب واحد" and scope_value:
            # محاولة العثور على مجلد مطابق
            for root, dirs, _ in os.walk(BOOKS_DIR):
                for dn in dirs:
                    if scope_value == dn or scope_value in dn:
                        book_dir_filter = os.path.join(root, dn)
                        break
                if book_dir_filter:
                    break

        raw = self.index.search_full(query, limit=80, book_dir_filter=book_dir_filter)
        rows: List[Tuple[str,int,int,float,str,str]] = []

        for r in raw:
            # display من book_dir
            book_dir = r.book_dir
            section = os.path.basename(os.path.dirname(book_dir))
            title = os.path.basename(book_dir)
            display = f"{section} | {title}"
            rows.append((book_dir, r.part_idx, r.page_idx, r.score, display, r.snippet))

        return rows

    def _search_hybrid(self, query: str, scope: str, scope_value: str) -> List[Tuple[str,int,int,float,str,str]]:
        # 1) نجلب نتائج Recoll أولاً (لتقليل التكلفة)
        hits = recoll_search(query, scope=scope, scope_value=scope_value, limit=80)

        if not hits:
            return []

        # 2) نحسب تضمين الاستعلام
        qv = self.backend.embed([query])[0]

        scored: List[Tuple[str,int,int,float,str,str]] = []
        for h in hits:
            book_dir = os.path.dirname(h.filepath)
            try:
                book = Book(book_dir)
                part_idx = next(i for i, p in enumerate(book.parts) if p.path == h.filepath)
                page_idx = book.parts[part_idx].page_for_line(h.line_num_1based - 1)

                page_text = book.parts[part_idx].pages[page_idx]
                mtime = 0.0
                try:
                    mtime = os.path.getmtime(h.filepath)
                except Exception:
                    pass

                vec = self.index.get_or_compute_page_vector(
                    book_dir=book_dir,
                    part_path=h.filepath,
                    part_idx=part_idx,
                    page_idx=page_idx,
                    title=book.title,
                    text=page_text,
                    mtime=mtime
                )

                score = self._cosine(qv, vec)
                scored.append((book_dir, part_idx, page_idx, float(score), h.display, h.snippet))
            except Exception:
                # نتجاوز ما لا يمكن قراءته
                continue

        scored.sort(key=lambda x: x[3], reverse=True)
        return scored[:80]

    def _cosine(self, a: List[float], b: List[float]) -> float:
        import math
        dot = 0.0
        na = 0.0
        nb = 0.0
        for x, y in zip(a, b):
            dot += x * y
            na += x * x
            nb += y * y
        if na <= 0 or nb <= 0:
            return 0.0
        return dot / math.sqrt(na * nb)

    def _fill_results(self, rows: List[Tuple[str,int,int,float,str,str]], query: str):
        self.store.clear()
        for r in rows:
            self.store.append(list(r))
        self._set_busy(False, f"النتائج: {len(rows)} — استعلام: {query}")
        return False

    def on_row_activated(self, tree, path, col):
        model = tree.get_model()
        it = model.get_iter(path)
        if not it:
            return
        book_dir = model.get_value(it, 0)
        part_idx = model.get_value(it, 1)
        page_idx = model.get_value(it, 2)

        try:
            book = Book(book_dir)
            words = self.entry.get_text().strip().split()
            self.open_cb(book, int(part_idx), int(page_idx), words)
        except Exception as e:
            self.status.set_label(f"فشل فتح النتيجة: {e}")

    def on_build_index(self, *args):
        if self._busy:
            return
        if not self.backend.available:
            self.status.set_label("الفهرسة الدلالية غير متاحة: ثبّت fastembed أو sentence-transformers.")
            return

        self._set_busy(True, "جاري بناء الفهرس الدلالي...")
        th = threading.Thread(target=self._build_index_thread, daemon=True)
        th.start()

    def _build_index_thread(self):
        try:
            chunks_batch = []
            total_chunks = 0

            # نجمع كل الكتب (مجلدات تحت الأقسام)
            for section in sorted(os.listdir(BOOKS_DIR)) if os.path.exists(BOOKS_DIR) else []:
                sec_path = os.path.join(BOOKS_DIR, section)
                if not os.path.isdir(sec_path):
                    continue
                for book_folder in sorted(os.listdir(sec_path)):
                    book_dir = os.path.join(sec_path, book_folder)
                    if not os.path.isdir(book_dir):
                        continue
                    try:
                        book = Book(book_dir)
                    except Exception:
                        continue

                    for part_idx, part in enumerate(book.parts):
                        if part.is_quran:
                            continue
                        try:
                            mtime = os.path.getmtime(part.path)
                        except Exception:
                            mtime = 0.0

                        # نحذف القديم لهذا الملف ثم نعيد إدراجه (أبسط وأكثر أماناً)
                        self.index.delete_for_part_if_mtime_changed(part.path, mtime)

                        for page_idx, page_text in enumerate(part.pages):
                            title = book.title
                            # نص المقطع: الصفحة كاملة
                            text = (page_text or "").strip()
                            if not text:
                                continue
                            chunks_batch.append((book_dir, part.path, part_idx, page_idx, title, text, mtime))
                            total_chunks += 1

                            if len(chunks_batch) >= 64:
                                self.index.upsert_chunks(chunks_batch)
                                chunks_batch.clear()
                                GLib.idle_add(self.status.set_label, f"فهرسة... تمّت إضافة {total_chunks} مقطعاً")

            if chunks_batch:
                self.index.upsert_chunks(chunks_batch)
                chunks_batch.clear()

            GLib.idle_add(self._set_busy, False, f"اكتملت الفهرسة الدلالية: {total_chunks} مقطعاً")
        except Exception as e:
            GLib.idle_add(self._set_busy, False, f"فشل بناء الفهرس: {e}")
