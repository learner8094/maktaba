# views/library_view.py
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, GLib, Gio
from typing import Callable
import threading

from services.app_update import AppUpdater
from services.library_scan import LibraryScanner
from services.library_update import LibraryUpdater


class LibraryView(Gtk.Box):
    def __init__(self, open_cb: Callable[[str], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.open_cb = open_cb
        self.scanner = LibraryScanner()
        self.updater = LibraryUpdater()
        self.app_updater = AppUpdater()

        # منع المكتبة من التمدد
        self.set_hexpand(False)
        self.set_vexpand(True)

        # شريط إجراءات المكتبة
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions.set_margin_top(8)
        actions.set_margin_start(10)
        actions.set_margin_end(10)

        self.btn_update = Gtk.Button(label="تحديث الكتب")
        self.btn_update.connect("clicked", self.on_update_clicked)
        actions.append(self.btn_update)

        self.btn_check_app_update = Gtk.Button(label="فحص نسخة جديدة")
        self.btn_check_app_update.connect("clicked", self.on_check_app_update_clicked)
        actions.append(self.btn_check_app_update)

        self.btn_apply_app_update = Gtk.Button(label="تحديث التطبيق")
        self.btn_apply_app_update.connect("clicked", self.on_apply_app_update_clicked)
        actions.append(self.btn_apply_app_update)

        self.append(actions)

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
        col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col.set_fixed_width(300)
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
        self.lbl_stats.set_xalign(0)
        self.lbl_stats.set_hexpand(True)
        self.lbl_stats.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_stats.set_single_line_mode(True)
        stats_box.append(self.lbl_stats)

        self.append(stats_box)

        self.load_books()

    def _set_status(self, message: str):
        self.lbl_stats.set_label(message)
        self.lbl_stats.set_tooltip_text(message)

    def load_books(self):
        self.store.clear()
        libs = self.scanner.refresh()
        total_books = sum(len(v) for v in libs.values())

        if total_books == 0:
            self._set_status("لا توجد كتب (تحقق من مجلد books)")
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

        self._set_status(f"إجمالي الكتب: {total_books}")

    def on_update_clicked(self, _btn):
        self.btn_update.set_sensitive(False)
        self._set_status("جاري تحديث الكتب من GitHub...")

        def worker():
            try:
                result = self.updater.update_new_books_safe()
                msg = (
                    f"تمت الإضافة: {result.added_books} كتاب | "
                    f"تم التخطي: {result.skipped_books} | "
                    f"الملفات المنزلة: {result.downloaded_files}"
                )
                GLib.idle_add(self._finish_update, msg, True)
            except Exception as e:
                GLib.idle_add(self._finish_update, str(e), False)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update(self, message: str, refresh: bool):
        self.btn_update.set_sensitive(True)
        if refresh:
            self.load_books()
        self._set_status(message)
        return False

    def on_check_app_update_clicked(self, _btn):
        self.btn_check_app_update.set_sensitive(False)
        self._set_status("جارٍ التحقق من آخر إصدار...")

        def worker():
            try:
                info = self.app_updater.safe_check_for_update()
                if info.update_available:
                    msg = f"متاح إصدار جديد: {info.latest_version} (الحالي: {info.current_version})"
                else:
                    msg = f"نسختك محدثة ({info.current_version})"
                GLib.idle_add(self._finish_app_update_check, msg)
            except Exception as e:
                GLib.idle_add(self._finish_app_update_check, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_app_update_check(self, message: str):
        self.btn_check_app_update.set_sensitive(True)
        self._set_status(message)
        return False

    def on_apply_app_update_clicked(self, _btn):
        if self.app_updater.is_flatpak():
            self._set_status("نسخة Flatpak: حدّث التطبيق من المتجر أو بالأمر: flatpak update io.github.maktaba")
            return

        release_url = f"https://github.com/{self.app_updater.repo}/releases"
        try:
            Gio.AppInfo.launch_default_for_uri(release_url, None)
            self._set_status("تم فتح صفحة الإصدارات. نزّل آخر نسخة وثبّتها.")
        except Exception:
            self._set_status(f"افتح يدويًا صفحة الإصدارات: {release_url}")

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
