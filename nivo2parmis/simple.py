"""منطق «یک‌کلیکی»: پیدا کردن فایل‌ها در یک پوشه و ادغام با تنظیمات خودکار."""
import glob, os
from .merge import merge


def find_files(folder):
    """(nivo, parmis): جدیدترین .nivo و .par داخل پوشه (یا None)."""
    def newest(pattern):
        fs = [f for f in glob.glob(os.path.join(folder, pattern))
              if os.path.isfile(f) and "merged" not in os.path.basename(f).lower()]
        return max(fs, key=os.path.getmtime) if fs else None
    return newest("*.nivo"), newest("*.par")


def default_output(parmis_path):
    folder = os.path.dirname(os.path.abspath(parmis_path))
    base = os.path.join(folder, "parmis-merged")
    out, i = base + ".par", 2
    while os.path.exists(out):                 # هرگز فایل قبلی را رونویسی نکن
        out, i = f"{base}-{i}.par", i + 1
    return out


def run_job(nivo, parmis, out=None, log=print):
    """ادغام با نگاشت خودکار. خروجی: (مسیر فایل خروجی، گزارش)."""
    out = out or default_output(parmis)
    report = merge(nivo, parmis, out, None, log=log)
    return out, report


def summary_text(report, out):
    lines = [f"✅ ادغام انجام شد", "",
             f"تراکنش‌های نیوو: {report['nivo_transactions']}  ←  سند جدید در پارمیس: {report['inserted']}",
             f"بازه‌ی تاریخ: {report['first_date']} تا {report['last_date']}",
             f"حساب جدید: {len(report['new_accounts'])}", "", "تغییر موجودی (به‌علاوه‌ی موجودی فعلی پارمیس):"]
    for b in report["balance_effect"]:
        lines.append(f"   {b['title']}: {b['effect']:+,.0f}")
    lines += ["", f"همه‌ی {len(report['checks'])} بررسی خودکار قبول شد.", "",
              "فایل خروجی:", out, "",
              "⚠️ قبل از «بازیابی» در پارمیس، از پارمیس فعلی خود پشتیبان بگیرید."]
    return "\n".join(lines)
