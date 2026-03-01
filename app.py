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
from config import BOOKS_DIR, STYLE_FILE, load_config, save_config, DEFAULT_CONFIG
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
        self.apply_theme_mode()

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

        settings_action = Gio.SimpleAction.new("settings", None)
        settings_action.connect("activate", self.show_settings_dialog)
        self.add_action(settings_action)

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
        if self.config.get("auto_reindex_on_startup", True) and needs_reindex():
            print("جاري تحديث الفهرسة...")
            ok, err = run_recollindex()
            if ok:
                print("تمت الفهرسة بنجاح.")
            else:
                print(f"فشل في إعادة الفهرسة: {err}")

        win = Gtk.ApplicationWindow(application=self)
        self.win = win
        win.set_title("مكتبة - الباحث في المكتبة الرقمية")
        win.set_default_size(1500, 900)

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
        menu.append("الإعدادات", "app.settings")
        menu.append("حول البرنامج", "app.about")
        menu.append("خروج", "app.quit")
        menu_button.set_menu_model(menu)

        self.notebook = Gtk.Notebook()
        win.set_child(self.notebook)

        # 1. لسان القرآن
        self.quran = QuranView(self.open_quran_book, self.save_position)
        self.notebook.append_page(self.quran, Gtk.Label(label="🕌 القرآن"))

        # 2. لسان القراءة
        library_view = LibraryView(self.open_book)
        library_view.set_size_request(320, -1)

        self.reader = ReaderView(self.save_position)
        self.reader.set_hexpand(True)
        self.reader.set_vexpand(True)
        self.reader.set_library_panel(library_view)

        self.notebook.append_page(self.reader, Gtk.Label(label="📖 القراءة"))

        # 3. لسان البحث
        self.search = SearchView(self.open_from_search)
        self.notebook.append_page(self.search, Gtk.Label(label="🔍 البحث"))

        # 4. لسان البحث الدلالي (بديل الذكاء الاصطناعي الثقيل)
        self.semantic = SemanticView(self.open_from_semantic)
        self.notebook.append_page(self.semantic, Gtk.Label(label="🧠 البحث الدلالي"))

        self.apply_runtime_settings()
        self.apply_theme_mode()
        win.present()

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
            self.reader.hide_sidebar_panel()
            self.save_position(book, page_idx)
        except Exception as e:
            print(f"فشل في الفتح من البحث: {e}")

    def open_from_semantic(self, book: Book, part_idx: int, page_idx: int, query_words: List[str]):
        """فتح نتيجة البحث الدلالي داخل القارئ مع تمييز كلمات الاستعلام إن أمكن"""
        try:
            self.reader.load_book(book, part_idx, page_idx, highlight_words=query_words)
            self.notebook.set_current_page(1)
            self.reader.hide_sidebar_panel()
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

    def apply_theme_mode(self):
        settings = Gtk.Settings.get_default()
        if not settings:
            return

        mode = self.config.get("theme_mode", DEFAULT_CONFIG["theme_mode"])

        # system = اترك GTK يتبع إعدادات النظام
        if mode == "system":
            settings.reset_property("gtk-application-prefer-dark-theme")
        else:
            settings.set_property("gtk-application-prefer-dark-theme", mode in {"dark", "dim"})

        win = getattr(self, "win", None)
        if not win:
            return

        for cls in ("theme-light", "theme-dark", "theme-dim"):
            win.remove_css_class(cls)

        if mode == "light":
            win.add_css_class("theme-light")
        elif mode == "dark":
            win.add_css_class("theme-dark")
        elif mode == "dim":
            win.add_css_class("theme-dim")

    def apply_runtime_settings(self):
        if hasattr(self, "reader") and self.reader:
            self.reader.font_size = self.config.get("font_size", DEFAULT_CONFIG["font_size"])
            self.reader.apply_font_size()
            self.reader.set_sidebar_width(self.config.get("reader_sidebar_width", DEFAULT_CONFIG["reader_sidebar_width"]))

        if hasattr(self, "quran") and self.quran:
            self.quran.font_size = self.config.get("quran_font_size", DEFAULT_CONFIG["quran_font_size"])
            self.quran.apply_font_size()
            self.quran.set_page_words(self.config.get("quran_page_words", DEFAULT_CONFIG["quran_page_words"]))

        self.apply_theme_mode()

    def show_settings_dialog(self, *_a):
        dialog = Gtk.Dialog(
            title="إعدادات البرنامج",
            transient_for=self.props.active_window,
            modal=True,
        )
        dialog.add_button("إلغاء", Gtk.ResponseType.CANCEL)
        dialog.add_button("حفظ", Gtk.ResponseType.OK)
        dialog.set_default_size(560, 460)

        content = dialog.get_content_area()
        content.set_margin_top(18)
        content.set_margin_bottom(18)
        content.set_margin_start(18)
        content.set_margin_end(18)

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.append(wrapper)

        title = Gtk.Label(label="تخصيص سريع")
        title.set_halign(Gtk.Align.START)
        title.add_css_class("title-3")
        wrapper.append(title)

        desc = Gtk.Label(label="خيارات أساسية فقط لتحسين تجربة القراءة والبحث")
        desc.set_halign(Gtk.Align.START)
        desc.add_css_class("dim-label")
        wrapper.append(desc)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("settings-card")
        wrapper.append(card)

        def add_scale_value(scale: Gtk.Scale, initial_value: float) -> Gtk.Label:
            value_label = Gtk.Label(label=str(int(initial_value)))
            value_label.set_width_chars(4)
            value_label.set_xalign(0.5)
            value_label.add_css_class("dim-label")

            def on_value_changed(s: Gtk.Scale):
                value_label.set_label(str(int(round(s.get_value()))))

            scale.connect("value-changed", on_value_changed)
            return value_label

        row_reader = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_reader = Gtk.Label(label="حجم خط القارئ")
        lbl_reader.set_halign(Gtk.Align.START)
        lbl_reader.set_hexpand(True)
        scale_reader = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 14, 60, 1)
        scale_reader.set_value(float(self.config.get("font_size", DEFAULT_CONFIG["font_size"])))
        scale_reader.set_digits(0)
        scale_reader.set_hexpand(True)
        lbl_reader_value = add_scale_value(scale_reader, scale_reader.get_value())
        row_reader.append(lbl_reader)
        row_reader.append(scale_reader)
        row_reader.append(lbl_reader_value)
        card.append(row_reader)

        row_quran = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_quran = Gtk.Label(label="حجم خط القرآن")
        lbl_quran.set_halign(Gtk.Align.START)
        lbl_quran.set_hexpand(True)
        scale_quran = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 12, 48, 1)
        scale_quran.set_value(float(self.config.get("quran_font_size", DEFAULT_CONFIG["quran_font_size"])))
        scale_quran.set_digits(0)
        scale_quran.set_hexpand(True)
        lbl_quran_value = add_scale_value(scale_quran, scale_quran.get_value())
        row_quran.append(lbl_quran)
        row_quran.append(scale_quran)
        row_quran.append(lbl_quran_value)
        card.append(row_quran)

        row_quran_lines = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_quran_lines = Gtk.Label(label="عدد كلمات صفحة القرآن")
        lbl_quran_lines.set_halign(Gtk.Align.START)
        lbl_quran_lines.set_hexpand(True)
        scale_quran_lines = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 40, 200, 5)
        scale_quran_lines.set_value(float(self.config.get("quran_page_words", DEFAULT_CONFIG["quran_page_words"])))
        scale_quran_lines.set_digits(0)
        scale_quran_lines.set_hexpand(True)
        lbl_quran_lines_value = add_scale_value(scale_quran_lines, scale_quran_lines.get_value())
        row_quran_lines.append(lbl_quran_lines)
        row_quran_lines.append(scale_quran_lines)
        row_quran_lines.append(lbl_quran_lines_value)
        card.append(row_quran_lines)

        row_sidebar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_sidebar = Gtk.Label(label="عرض القائمة الجانبية")
        lbl_sidebar.set_halign(Gtk.Align.START)
        lbl_sidebar.set_hexpand(True)
        scale_sidebar = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 180, 420, 10)
        scale_sidebar.set_value(float(self.config.get("reader_sidebar_width", DEFAULT_CONFIG["reader_sidebar_width"])))
        scale_sidebar.set_digits(0)
        scale_sidebar.set_hexpand(True)
        lbl_sidebar_value = add_scale_value(scale_sidebar, scale_sidebar.get_value())
        row_sidebar.append(lbl_sidebar)
        row_sidebar.append(scale_sidebar)
        row_sidebar.append(lbl_sidebar_value)
        card.append(row_sidebar)

        row_theme = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_theme = Gtk.Label(label="مظهر البرنامج")
        lbl_theme.set_halign(Gtk.Align.START)
        lbl_theme.set_hexpand(True)
        combo_theme = Gtk.ComboBoxText()
        combo_theme.append("system", "وضع النظام")
        combo_theme.append("light", "وضع فاتح")
        combo_theme.append("dark", "وضع داكن")
        combo_theme.append("dim", "وضع مظلم")
        theme_mode = self.config.get("theme_mode", DEFAULT_CONFIG["theme_mode"])
        if not combo_theme.set_active_id(theme_mode):
            combo_theme.set_active_id(DEFAULT_CONFIG["theme_mode"])
        row_theme.append(lbl_theme)
        row_theme.append(combo_theme)
        card.append(row_theme)

        row_reindex = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_reindex = Gtk.Label(label="تحديث الفهرسة تلقائياً عند التشغيل")
        lbl_reindex.set_halign(Gtk.Align.START)
        lbl_reindex.set_hexpand(True)
        switch_reindex = Gtk.Switch()
        switch_reindex.set_active(bool(self.config.get("auto_reindex_on_startup", True)))
        row_reindex.append(lbl_reindex)
        row_reindex.append(switch_reindex)
        card.append(row_reindex)

        def on_response(dlg, resp):
            if resp == Gtk.ResponseType.OK:
                self.config["font_size"] = int(scale_reader.get_value())
                self.config["quran_font_size"] = int(scale_quran.get_value())
                self.config["quran_page_words"] = int(scale_quran_lines.get_value())
                self.config["reader_sidebar_width"] = int(scale_sidebar.get_value())
                self.config["theme_mode"] = combo_theme.get_active_id() or DEFAULT_CONFIG["theme_mode"]
                self.config["auto_reindex_on_startup"] = bool(switch_reindex.get_active())
                save_config(self.config)
                self.apply_runtime_settings()
            dlg.destroy()

        dialog.connect("response", on_response)
        dialog.present()

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
