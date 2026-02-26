#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مكتبة - قارئ وباحث الكتب العربية
تطبيق مفتوح المصدر لقراءة والبحث في الكتب والقرآن الكريم
"""

import sys


# === التحقق من المكتبات المطلوبة ===
def check_requirements():
    """التحقق من توفر المكتبات الأساسية"""
    missing = []

    try:
        import gi
        gi.require_version('Gtk', '4.0')
        from gi.repository import Gtk
    except ImportError:
        missing.append('PyGObject (GTK4)')
    except ValueError:
        missing.append('GTK4')

    if missing:
        print("=" * 60)
        print("⚠️  مكتبات مطلوبة غير موجودة!")
        print("=" * 60)
        for lib in missing:
            print(f"  ❌ {lib}")
        print()
        print("📦 للتثبيت:")
        print("  ثبّت PyGObject و GTK4 حسب توزيعتك، ثم أعد تشغيل التطبيق.")
        print("  راجع ملف README.md لقائمة المتطلبات وطرق التشغيل.")
        print("=" * 60)
        sys.exit(1)


# التحقق من المتطلبات
check_requirements()


# === استيراد التطبيق وتشغيله ===
try:
    from app import MainApp

    def main():
        """نقطة الدخول الرئيسية للبرنامج"""
        app = MainApp()
        try:
            exit_code = app.run(None)
            sys.exit(exit_code)
        except KeyboardInterrupt:
            print("\n👋 تم إيقاف البرنامج")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ خطأ في تشغيل البرنامج: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    if __name__ == "__main__":
        main()

except ImportError as e:
    print("=" * 60)
    print("❌ خطأ في استيراد التطبيق!")
    print("=" * 60)
    print(f"التفاصيل: {e}")
    print()
    print("تأكد من:")
    print("  1. وجود جميع ملفات المشروع")
    print("  2. أنك في المجلد الصحيح")
    print("  3. تثبيت جميع المكتبات المطلوبة")
    print()
    print("📖 راجع README.md")
    print("=" * 60)
    sys.exit(1)
