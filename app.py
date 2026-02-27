# app.py
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk
import os
from typing import List, Optional
import threading

# استيراد الواجهات
from views.library_view import LibraryView
from views.reader_view import ReaderView
from views.search_view import SearchView
from views.quran_view import QuranView
from views.semantic_view import SemanticView

from book import Book
from config import BOOKS_DIR, STYLE_FILE, load_config, save_config
from services.indexing import needs_reindex, run_recollindex
from services.app_update import AppUpdater

class MainApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.maktaba",
            flags=Gio.ApplicationFlags.HANDLES_OPEN
        )
        GLib.set_prgname("maktaba")
        GLib.set_application_name("مكتبة")
        self.config = load_config()
        if "last_positions" not in self.config:
            self.config["last_positions"] = {}
        self.app_updater = AppUpdater()

    def do_startup(self):
        Gtk.Application.do_startup(self)

        # تحميل ملف الستايل CSS
        self.load_css()

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda a, p: self.quit())
        self.add_action(quit_action)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.show_about)
        self.add_action(about_action)

        check_app_update_action = Gio.SimpleAction.new("check_app_update", None)
        check_app_update_action.connect("activate", self.on_check_app_update)
        self.add_action(check_app_update_action)

        apply_app_update_action = Gio.SimpleAction.new("apply_app_update", None)
        apply_app_update_action.connect("activate", self.on_apply_app_update)
        self.add_action(apply_app_update_action)

    def load_css(self):
        """تحميل وتطبيق ملف التنسيقات الخارجي"""
        if os.path.exists(STYLE_FILE):
            provider = Gtk.CssProvider()
            try:
                provider.load_from_path(STYLE_FILE)
                Gtk.StyleContext.add_provider_for_display(
                    Gdk.Display.get_default(),
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            except Exception as e:
                print(f"فشل تحميل ملف الستايل: {e}")

    def do_activate(self):
        Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
        win = self.props.active_window
        if win:
            win.present()
            return

        # تحديث الفهرسة تلقائياً مرة عند فتح البرنامج
        if needs_reindex():
            print("جاري تحديث الفهرسة...")
            ok, err = run_recollindex()
            if ok:
                print("تمت الفهرسة بنجاح.")
            else:
                print(f"فشل في إعادة الفهرسة: {err}")

        win = Gtk.ApplicationWindow(application=self)
        win.set_title("مكتبة - الباحث في المكتبة الرقمية")
        # حجم افتراضي مناسب لمعظم الشاشات المتوسطة دون تجاوز الارتفاع
        win.set_default_size(1200, 760)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_global_key_pressed)
        win.add_controller(key_ctrl)

        header = Gtk.HeaderBar()
        win.set_titlebar(header)

        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        header.pack_end(menu_button)

        menu = Gio.Menu()
        menu.append("فحص نسخة جديدة", "app.check_app_update")
        menu.append("تحديث التطبيق", "app.apply_app_update")
        menu.append("حول البرنامج", "app.about")
        menu.append("خروج", "app.quit")
        menu_button.set_menu_model(menu)

        self.notebook = Gtk.Notebook()
        win.set_child(self.notebook)

        # 1. لسان القرآن
        self.quran = QuranView(self.open_quran_book, self.save_position)
        self.notebook.append_page(self.quran, self._build_tab_label("bookmarks-symbolic", "القرآن"))

        # 2. لسان القراءة
        read_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)

        library_view = LibraryView(self.open_book)
        library_view.set_size_request(320, -1)

        self.lib_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_RIGHT, reveal_child=True)
        self.lib_revealer.set_child(library_view)

        self.reader = ReaderView(self.save_position)
        self.reader.set_hexpand(True)
        self.reader.set_vexpand(True)

        def toggle_library_sidebar():
            show_library = not self.lib_revealer.get_reveal_child()
            self.lib_revealer.set_reveal_child(show_library)
            if show_library:
                self.reader.hide_sidebar_panel()

        self.reader.connect_library_toggle(toggle_library_sidebar)
        self.reader.connect_sidebar_panel_requested(lambda _name: self.lib_revealer.set_reveal_child(False))

        read_paned.set_start_child(self.lib_revealer)
        read_paned.set_end_child(self.reader)
        read_paned.set_resize_start_child(True)
        read_paned.set_shrink_start_child(False)
        read_paned.set_position(320)

        self.notebook.append_page(read_paned, self._build_tab_label("document-open-symbolic", "القراءة"))

        # 3. لسان البحث
        self.search = SearchView(self.open_from_search)
        self.notebook.append_page(self.search, self._build_tab_label("system-search-symbolic", "البحث"))

        # 4. لسان البحث الدلالي (بديل الذكاء الاصطناعي الثقيل)
        self.semantic = SemanticView(self.open_from_semantic)
        self.notebook.append_page(self.semantic, self._build_tab_label("edit-find-symbolic", "البحث الدلالي"))

        win.present()

    def _build_tab_label(self, icon_name: str, text: str) -> Gtk.Widget:
        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_icon_size(Gtk.IconSize.NORMAL)

        label = Gtk.Label(label=text)

        tab_box.append(icon)
        tab_box.append(label)
        return tab_box

    def on_global_key_pressed(self, controller, keyval, keycode, state):
        if keyval not in (Gdk.KEY_F5, Gdk.KEY_F6):
            return False

        current_tab = self.notebook.get_current_page()
        is_next = keyval == Gdk.KEY_F5

        if current_tab == 0 and self.quran:
            self.quran.next_pg() if is_next else self.quran.prev_pg()
            return True

        if current_tab == 1 and self.reader:
            self.reader.next_page() if is_next else self.reader.prev_page()
            return True

        if current_tab == 2 and self.search:
            self.search.select_adjacent_result(1 if is_next else -1)
            return True

        return False

    def save_position(self, book: Book, page: int):
        if not book:
            return
        try:
            rel = os.path.relpath(book.dir, BOOKS_DIR)
            self.config.setdefault("last_positions", {})[rel] = {"page": page}
            save_config(self.config)
        except Exception as e:
            print(f"فشل في حفظ الموقع: {e}")

    def open_book(self, path: str):
        try:
            book = Book(path)
            rel = os.path.relpath(book.dir, BOOKS_DIR)
            pos = self.config.get("last_positions", {}).get(rel, {})
            page = pos.get("page", 0)

            self.reader.load_book(book, 0, page)
            self.notebook.set_current_page(1)
            self.save_position(book, page)
        except Exception as e:
            print(f"فشل في فتح الكتاب: {e}")

    def open_from_search(self, book: Book, part_idx: int, page_idx: int, words: List[str], line_idx: Optional[int] = None):
        try:
            self.reader.load_book(book, part_idx, page_idx, highlight_words=words, line_to_scroll=line_idx)
            self.notebook.set_current_page(1)
            self.lib_revealer.set_reveal_child(False)
            self.save_position(book, page_idx)
        except Exception as e:
            print(f"فشل في الفتح من البحث: {e}")

    def open_from_semantic(self, book: Book, part_idx: int, page_idx: int, query_words: List[str]):
        """فتح نتيجة البحث الدلالي داخل القارئ مع تمييز كلمات الاستعلام إن أمكن"""
        try:
            self.reader.load_book(book, part_idx, page_idx, highlight_words=query_words)
            self.notebook.set_current_page(1)
            self.lib_revealer.set_reveal_child(False)
            self.save_position(book, page_idx)
        except Exception as e:
            print(f"فشل في الفتح من البحث الدلالي: {e}")

    def open_quran_book(self, book: Book, page: int = 0, words: Optional[List[str]] = None):
        try:
            self.quran.load_book_object(book, page, words)
            self.save_position(book, page)
        except Exception as e:
            print(f"فشل في فتح القرآن: {e}")


    def _show_message_dialog(self, message: str, message_type: Gtk.MessageType = Gtk.MessageType.INFO):
        dlg = Gtk.MessageDialog(
            transient_for=self.props.active_window,
            modal=True,
            buttons=Gtk.ButtonsType.OK,
            message_type=message_type,
            text=message,
        )
        dlg.connect("response", lambda d, r: d.destroy())
        dlg.present()

    def on_check_app_update(self, *_a):
        self._show_message_dialog("جارٍ التحقق من آخر إصدار...")

        def worker():
            try:
                info = self.app_updater.safe_check_for_update()
                if info.update_available:
                    msg = f"متاح إصدار جديد: {info.latest_version} (الحالي: {info.current_version})"
                else:
                    msg = f"نسختك محدثة ({info.current_version})"
                GLib.idle_add(self._show_message_dialog, msg)
            except Exception as e:
                GLib.idle_add(self._show_message_dialog, str(e), Gtk.MessageType.ERROR)

        threading.Thread(target=worker, daemon=True).start()

    def on_apply_app_update(self, *_a):
        if self.app_updater.is_flatpak():
            self._show_message_dialog("نسخة Flatpak: حدّث التطبيق من المتجر أو بالأمر: flatpak update io.github.maktaba")
            return

        release_url = f"https://github.com/{self.app_updater.repo}/releases"
        try:
            Gio.AppInfo.launch_default_for_uri(release_url, None)
            self._show_message_dialog("تم فتح صفحة الإصدارات. نزّل آخر نسخة وثبّتها.")
        except Exception:
            self._show_message_dialog(f"افتح يدويًا صفحة الإصدارات: {release_url}", Gtk.MessageType.ERROR)

    def show_about(self, *a):
        dlg = Gtk.AboutDialog(
            transient_for=self.props.active_window,
            modal=True,
            program_name="مكتبة",
            version="0.6",
            comments="قارئ وباحث كتب إسلامية مفتوح المصدر",
            license_type=Gtk.License.GPL_3_0,
            authors=["maktaba"],
        )
        dlg.present()
