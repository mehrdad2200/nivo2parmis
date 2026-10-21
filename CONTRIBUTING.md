# مشارکت

```bash
pip install -e ".[dev]"
python -m pytest -q
```

* تست‌ها از داده‌ی **ساختگی** (`examples/make_example_data.py`) استفاده می‌کنند. هرگز فایل واقعی پشتیبان را commit نکنید.
* `examples/parmis_template.par` فقط ساختار جدول‌ها و حساب‌های پیش‌فرض پارمیس را دارد، بدون تراکنش و اطلاعات شخصی.
* اگر نسخه‌ی جدیدی از پارمیس ساختار دیتابیس را عوض کرد: ساختار را با `docs/format-parmis.md` مقایسه کنید،
  `TESTED_PARMIS_DB_VERSIONS` را در `nivo2parmis/merge.py` به‌روز کنید و تست‌ها را اجرا کنید.
* Issue می‌زنید؟ خروجی `inspect` (بدون یادداشت‌ها) و پیام خطا را بگذارید، نه خود فایل پشتیبان را.
