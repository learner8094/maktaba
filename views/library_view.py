# views/library_view.py
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango
from typing import Callable

from services.library_scan import LibraryScanner

class LibraryView(Gtk.Box):
    def __init__(self, open_cb: Callable[[str], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.open_cb = open_cb
        self.scanner = LibraryScanner()

        # منع المكتبة من التمدد
        self.set_hexpand(False)
        self.set_vexpand(True)

        # وعاء القائمة
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        # إعداد الشجرة
        self.store = Gtk.TreeStore(str, str)  # (Display Text, Filepath)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(False)
        self.tree.set_enable_tree_lines(True)
        self.tree.connect("row-activated", self.on_row_activated)

        rend = Gtk.CellRendererText()
        rend.set_property("ellipsize", Pango.EllipsizeMode.END)
        rend.set_property("xpad", 10)
        rend.set_property("ypad", 8)

        col = Gtk.TreeViewColumn("المكتبة", rend, text=0)
        col.set_expand(True)
        col.set_resizable(True)
        self.tree.append_column(col)

        scroll.set_child(self.tree)

        # شريط الإحصائيات السفلي
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        stats_box.add_css_class("stats-bar")
        stats_box.set_margin_top(6)
        stats_box.set_margin_bottom(6)
        stats_box.set_margin_start(10)
        stats_box.set_margin_end(10)

        self.lbl_stats = Gtk.Label(label="جاري التحميل...")
        stats_box.append(self.lbl_stats)

        self.append(stats_box)

        self.load_books()

    def load_books(self):
        self.store.clear()
        libs = self.scanner.refresh()
        total_books = sum(len(v) for v in libs.values())

        if total_books == 0:
            self.lbl_stats.set_label("لا توجد كتب (تحقق من مجلد books)")
            return

        for section_name, books in libs.items():
            sec_display = f"{section_name} ({len(books)})"
            sec_iter = self.store.append(None, [sec_display, None])

            for info in books:
                # إظهار: عنوان - مؤلف
                display = info.title
                if info.author:
                    display = f"{info.title} - {info.author}"
                self.store.append(sec_iter, [display, info.dir_path])

        self.lbl_stats.set_label(f"إجمالي الكتب: {total_books}")

    def on_row_activated(self, view, path, col):
        it = self.store.get_iter(path)
        filepath = self.store.get_value(it, 1)
        if filepath:
            self.open_cb(filepath)
        else:
            if view.row_expanded(path):
                view.collapse_row(path)
            else:
                view.expand_row(path, False)
