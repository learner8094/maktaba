# views/reader_view.py
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, Gdk, GLib
from typing import Optional, List, Callable
import os

from book import Book
from config import load_config, save_config

CONFIG = load_config()

class ReaderView(Gtk.Box):
    def __init__(self, save_cb: Callable[[Book, int], None]):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.set_direction(Gtk.TextDirection.RTL)
        self.save_cb = save_cb
        self.book: Optional[Book] = None
        self.font_size = CONFIG.get("font_size", 22)
        
        # إعدادات التمدد
        self.set_hexpand(True)
        self.set_vexpand(True)
        
        # 1. القائمة الجانبية (الفهرس)
        self.sidebar_revealer = Gtk.Revealer()
        self.sidebar_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_LEFT)
        self.sidebar_revealer.set_reveal_child(True) 
        self.append(self.sidebar_revealer)

        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_box.set_size_request(280, -1)
        sidebar_box.add_css_class("sidebar") # الستايل الآن في style.css
        
        lbl_toc = Gtk.Label(label="فهرس الكتاب")
        lbl_toc.set_margin_top(15)
        lbl_toc.set_margin_bottom(10)
        lbl_toc.add_css_class("title-4")
        sidebar_box.append(lbl_toc)

        self.section_store = Gtk.TreeStore(str, int, int, int)
        self.section_view = Gtk.TreeView(model=self.section_store)
        self.section_view.set_headers_visible(False)
        self.section_view.set_enable_tree_lines(True)
        
        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        renderer.set_property("xpad", 10)
        renderer.set_property("ypad", 8)
        
        col = Gtk.TreeViewColumn("الفصل", renderer, text=0)
        col.set_expand(True)
        col.set_resizable(True)
        self.section_view.append_column(col)
        
        self.section_view.get_selection().connect("changed", self.on_section_selected)
        
        sec_scroll = Gtk.ScrolledWindow()
        sec_scroll.set_child(self.section_view)
        sec_scroll.set_vexpand(True)
        sec_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sidebar_box.append(sec_scroll)
        
        self.sidebar_revealer.set_child(sidebar_box)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # 2. منطقة القراءة الرئيسية
        main_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_area.set_hexpand(True)
        main_area.set_vexpand(True)
        self.append(main_area)

        # الشريط العلوي
        top_bar = Gtk.Box(spacing=6)
        top_bar.set_margin_start(10)
        top_bar.set_margin_end(10)
        top_bar.set_margin_top(8)
        top_bar.set_margin_bottom(8)
        top_bar.set_hexpand(True) 
        main_area.append(top_bar)

        self.btn_lib_toggle = Gtk.Button.new_from_icon_name("view-grid-symbolic")
        self.btn_lib_toggle.set_tooltip_text("إظهار/إخفاء المكتبة")
        top_bar.append(self.btn_lib_toggle)
        
        top_bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        btn_sidebar = Gtk.Button.new_from_icon_name("view-list-symbolic")
        btn_sidebar.set_tooltip_text("إظهار/إخفاء الفهرس")
        btn_sidebar.connect("clicked", lambda x: self.sidebar_revealer.set_reveal_child(
            not self.sidebar_revealer.get_reveal_child()))
        top_bar.append(btn_sidebar)

        self.lbl_book_title = Gtk.Label(label="")
        self.lbl_book_title.set_hexpand(True) 
        self.lbl_book_title.add_css_class("title-4")
        self.lbl_book_title.set_ellipsize(Pango.EllipsizeMode.END)
        top_bar.append(self.lbl_book_title)

        self.btn_info = Gtk.Button.new_from_icon_name("info-symbolic")
        self.btn_info.set_tooltip_text("بطاقة الكتاب")
        self.btn_info.connect("clicked", self.show_book_info)
        top_bar.append(self.btn_info)

        top_bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        box_font = Gtk.Box()
        box_font.add_css_class("linked")
        btn_font_inc = Gtk.Button.new_from_icon_name("zoom-in-symbolic")
        btn_font_inc.connect("clicked", lambda x: self.change_font(2))
        btn_font_dec = Gtk.Button.new_from_icon_name("zoom-out-symbolic")
        btn_font_dec.connect("clicked", lambda x: self.change_font(-2))
        box_font.append(btn_font_inc)
        box_font.append(btn_font_dec)
        top_bar.append(box_font)

        # وعاء النص
        self.text = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD)
        self.text.add_css_class("reader-text") # ربط بالكلاس في style.css
        self.text.set_hexpand(True)
        self.text.set_vexpand(True)
        self.text.set_justification(Gtk.Justification.FILL)
        
        self.buffer = self.text.get_buffer()
        self.highlight_tag = self.buffer.create_tag("hl", background="#f1c40f", foreground="#000000")

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.text)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        main_area.append(scroll)
        
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_key_pressed)
        self.text.add_controller(key_ctrl)

        # الشريط السفلي للملاحة
        bottom_bar = Gtk.Box(spacing=12)
        bottom_bar.set_margin_start(20)
        bottom_bar.set_margin_end(20)
        bottom_bar.set_margin_top(10)
        bottom_bar.set_margin_bottom(10)
        main_area.append(bottom_bar)

        self.btn_first = Gtk.Button.new_from_icon_name("media-skip-backward-symbolic") 
        self.btn_prev = Gtk.Button.new_from_icon_name("go-previous-symbolic") 
        self.btn_next = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self.btn_last = Gtk.Button.new_from_icon_name("media-skip-forward-symbolic")

        self.btn_first.connect("clicked", lambda x: self.goto_first_page())
        self.btn_prev.connect("clicked", lambda x: self.prev_page())
        self.btn_next.connect("clicked", lambda x: self.next_page())
        self.btn_last.connect("clicked", lambda x: self.goto_last_page())

        self.page_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.page_scale.set_hexpand(True)
        self.page_scale.set_draw_value(False)
        self.page_scale.connect("value-changed", self.on_scale_changed)

        self.lbl_page_num = Gtk.Label(label="0 / 0")
        self.lbl_page_num.set_width_chars(10)

        bottom_bar.append(self.btn_first)
        bottom_bar.append(self.btn_prev)
        bottom_bar.append(self.page_scale)
        bottom_bar.append(self.lbl_page_num)
        bottom_bar.append(self.btn_next)
        bottom_bar.append(self.btn_last)

        # مزود CSS خاص بحجم الخط فقط (لأنه ديناميكي)
        self.font_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), 
            self.font_provider, 
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.apply_font_size()

    def apply_font_size(self):
        """تطبيق حجم الخط الديناميكي فقط"""
        css = f".reader-text {{ font-size: {self.font_size}px; }}"
        self.font_provider.load_from_data(css.encode())

    def show_book_info(self, *args):
        if not self.book or not self.book.meta:
            dlg = Gtk.MessageDialog(
                transient_for=self.get_native(),
                modal=True,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="معلومات الكتاب",
                secondary_text=f"العنوان: {self.book.title if self.book else 'غير معروف'}"
            )
            dlg.connect("response", lambda d, r: d.destroy())
            dlg.present()
            return

        m = self.book.meta
        author_info = m.get("author", {})
        if isinstance(author_info, dict):
            auth_name = author_info.get("name", "غير معروف")
            auth_death = author_info.get("death_year", "")
            auth_str = f"{auth_name} ({auth_death})" if auth_death else auth_name
        else:
            auth_str = str(author_info)

        info_text = (
            f"📖 الكتاب: {m.get('title', self.book.title)}\n"
            f"👤 المؤلف: {auth_str}\n"
            f"📁 التصنيف: {m.get('category', '')} - {m.get('sub_category', '')}\n"
            f"🌐 اللغة: {m.get('language', 'ar')}\n"
            f"📜 الرخصة: {m.get('license', 'غير محددة')}\n"
            f"🔗 المصدر: {m.get('source', {}).get('name', 'الشاملة')}"
        )

        dlg = Gtk.MessageDialog(
            transient_for=self.get_native(),
            modal=True,
            message_type=Gtk.MessageType.OTHER,
            buttons=Gtk.ButtonsType.OK,
            text="بطاقة الكتاب",
            secondary_text=info_text
        )
        dlg.set_direction(Gtk.TextDirection.RTL)
        dlg.connect("response", lambda d, r: d.destroy())
        dlg.present()

    def connect_library_toggle(self, callback: Callable):
        self.btn_lib_toggle.connect("clicked", lambda x: callback())

    def change_font(self, d: int):
        self.font_size = max(14, min(60, self.font_size + d))
        CONFIG["font_size"] = self.font_size
        save_config(CONFIG)
        self.apply_font_size()

    def load_book(self, book: Book, part_index: int=0, page_index: int=0, 
                  highlight_words: Optional[List[str]]=None, line_to_scroll: Optional[int]=None):
        self.book = book
        display_title = book.title
        if book.author:
            display_title = f"{book.title} - {book.author}"
        self.lbl_book_title.set_label(display_title)
        
        self.section_store.clear()
        parents = {} 
        for p_idx, part in enumerate(book.parts):
            for title, line, level in part.sections:
                pg_idx = part.page_for_line(line)
                parent_iter = parents.get(level - 1) if level > 1 else None
                current_iter = self.section_store.append(parent_iter, [title, p_idx, pg_idx, line])
                parents[level] = current_iter
                for k in [k for k in parents if k > level]: del parents[k]

        self.book.goto_page(part_index, page_index)
        self.update_ui(highlight_words, line_to_scroll)

    def update_ui(self, highlight_words: Optional[List[str]]=None, line_to_scroll: Optional[int]=None):
        if not self.book: return
        
        self.buffer.set_text(self.book.current_page)
        self.buffer.remove_tag(self.highlight_tag, self.buffer.get_start_iter(), self.buffer.get_end_iter())
        
        if line_to_scroll is not None:
            GLib.timeout_add(50, self._scroll_to_line, line_to_scroll)

        if highlight_words:
            start = self.buffer.get_start_iter()
            for word in highlight_words:
                while True:
                    match = start.forward_search(word, Gtk.TextSearchFlags.CASE_INSENSITIVE, self.buffer.get_end_iter())
                    if not match: break
                    s, e = match
                    self.buffer.apply_tag(self.highlight_tag, s, e)
                    start = e
        
        current_part_len = len(self.book.current_part.pages)
        current = self.book.current_page_index + 1
        self.page_scale.freeze_notify()
        self.page_scale.set_range(1, max(1, current_part_len))
        self.page_scale.set_value(current)
        self.page_scale.thaw_notify()
        self.lbl_page_num.set_label(f"{current} / {current_part_len}")
        
        if self.save_cb:
            self.save_cb(self.book, self.book.current_page_index)

    def _scroll_to_line(self, line_to_scroll: int):
        if not self.book: return False
        
        start_line_of_page = self.book.current_part.get_start_line_for_page(self.book.current_page_index)
        relative_line = line_to_scroll - start_line_of_page
        
        line_count = self.buffer.get_line_count()
        relative_line = max(0, min(relative_line, line_count - 1))
        
        iter_at_line = self.buffer.get_iter_at_line(relative_line)
        self.buffer.place_cursor(iter_at_line)
        self.text.scroll_to_iter(iter_at_line, 0.0, True, 0.0, 0.0)
        
        return False

    def on_section_selected(self, sel):
        model, iter_ = sel.get_selected()
        if iter_ and self.book:
            part_idx = model.get_value(iter_, 1)
            page_idx = model.get_value(iter_, 2)
            line_idx = model.get_value(iter_, 3)
            
            self.book.goto_page(part_idx, page_idx)
            self.update_ui(line_to_scroll=line_idx)

    def on_scale_changed(self, scale):
        if not self.book: return
        val = int(scale.get_value()) - 1
        if val != self.book.current_page_index:
            self.book.goto_page(self.book.current_part_index, val)
            self.update_ui()

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Right:
            self.prev_page(); return True
        elif keyval == Gdk.KEY_Left:
            self.next_page(); return True
        return False

    def next_page(self):
        if self.book: self.book.next_page(); self.update_ui()
    def prev_page(self):
        if self.book: self.book.prev_page(); self.update_ui()
    def goto_first_page(self):
        if self.book: self.book.goto_page(0, 0); self.update_ui()
    def goto_last_page(self):
        if self.book:
            lp = len(self.book.parts) - 1
            self.book.goto_page(lp, len(self.book.parts[lp].pages) - 1)
            self.update_ui()
