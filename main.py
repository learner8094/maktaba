#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مكتبة - قارئ وباحث الكتب العربية
تطبيق مفتوح المصدر لقراءة والبحث في الكتب والقرآن الكريم
"""

import os
import sys

# === تفعيل البيئة الافتراضية تلقائياً ===
# هذا الكود يبحث عن مجلد venv ويفعّله تلقائياً إذا وُجد
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PATH = os.path.join(BASE_DIR, 'venv')

def activate_virtualenv():
    """تفعيل البيئة الافتراضية إذا كانت موجودة"""
    if not os.path.exists(VENV_PATH):
        return False
    
    # مسارات البيئة الافتراضية
    if sys.platform == 'win32':
        activate_script = os.path.join(VENV_PATH, 'Scripts', 'activate_this.py')
        venv_python = os.path.join(VENV_PATH, 'Scripts', 'python.exe')
    else:
        activate_script = os.path.join(VENV_PATH, 'bin', 'activate_this.py')
        venv_python = os.path.join(VENV_PATH, 'bin', 'python3')
    
    # إذا لم نكن نعمل من python البيئة الافتراضية، أعد التشغيل
    if sys.executable != venv_python and os.path.exists(venv_python):
        # إعادة تشغيل البرنامج باستخدام python البيئة الافتراضية
        os.execv(venv_python, [venv_python] + sys.argv)
        return True
    
    return True

# محاولة تفعيل البيئة الافتراضية
venv_activated = activate_virtualenv()

# إضافة مجلد المشروع نفسه إلى sys.path
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

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
        print()
        
        if venv_activated:
            print("  أنت تستخدم بيئة افتراضية (✅ موصى به)")
            print("  قم بتفعيل البيئة أولاً:")
            print(f"    source {os.path.relpath(VENV_PATH)}/bin/activate")
            print()
            print("  ثم ثبّت المكتبات:")
            print("    pip install PyGObject")
        else:
            print("  ⚠️  أنت لا تستخدم بيئة افتراضية!")
            print()
            print("  الطريقة الآمنة (موصى بها):")
            print("    python3 -m venv venv")
            print("    source venv/bin/activate")
            print("    pip install PyGObject")
            print()
            print("  أو استخدم سكريبت التشغيل:")
            print("    ./run.sh")
        
        print()
        print("📖 للمزيد من التفاصيل، راجع: INSTALL_CHIMERA.md")
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
    print("📖 راجع README.md أو INSTALL_CHIMERA.md")
    print("=" * 60)
    sys.exit(1)
