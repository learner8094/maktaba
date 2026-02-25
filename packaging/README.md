# Packaging

## الحزمة المختارة: Flatpak

تم اعتماد **Flatpak** لأنه أسهل خيار لتوفير تجربة تثبيت موحدة على توزيعات Linux المختلفة،
مع عزل جيد للتطبيق واعتماده على Runtime ثابت (GNOME Platform).

## المحتوى داخل هذا المجلد

- `flatpak/io.github.maktaba.yml`
  - Manifest أساسي لبناء التطبيق باسم `io.github.maktaba`.
  - يثبت ملف سطح المكتب في:
    - `/app/share/applications/io.github.maktaba.desktop`
  - يثبت الأيقونة في:
    - `/app/share/icons/hicolor/scalable/apps/io.github.maktaba.svg`
- `flatpak/io.github.maktaba.desktop`
  - تعريف التطبيق في قائمة التطبيقات.
- `flatpak/io.github.maktaba.svg`
  - أيقونة التطبيق باسم `io.github.maktaba`.

## ملاحظات

- المسارات داخل Flatpak تبدأ بـ`/app`، وهي تقابل ما يتوقعه النظام كمحتوى `share/` داخل الحزمة.
- يمكن لاحقاً إضافة `metainfo.xml` للتحسينات الخاصة بمخازن التطبيقات (مثل GNOME Software).
