# داده‌ی نمونه

همه‌ی فایل‌های این پوشه **ساختگی** هستند.

| فایل | توضیح |
|---|---|
| `sample_nivo.nivo` | پشتیبان نیوو (رمزشده) با ۸۸ تراکنش: درآمد، هزینه، زیردسته، دو انتقال (یکی با اختلاف ۵٬۶۰۰)، پروژه و یک تراکنش بدون دسته |
| `sample_parmis.par` | پشتیبان پارمیس با ۳ سند در ماه‌های بعد |
| `sample_mapping.json` | فایل نگاشت ساخته‌شده با `init-mapping` |
| `sample_merged.par` | خروجی ادغام |
| `parmis_template.par` | ساختار خالی پارمیس + حساب‌های پیش‌فرض (برای تست) |
| `make_example_data.py` | بازسازی فایل‌های نمونه (`pip install jdatetime`) |

```bash
nivo2parmis init-mapping --nivo sample_nivo.nivo --parmis sample_parmis.par -o sample_mapping.json
nivo2parmis merge --nivo sample_nivo.nivo --parmis sample_parmis.par -o sample_merged.par --mapping sample_mapping.json
```
