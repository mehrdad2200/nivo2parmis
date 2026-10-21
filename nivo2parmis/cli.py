"""خط فرمان:  python -m nivo2parmis <دستور> ..."""
import argparse, json, sqlite3, sys
from . import __version__
from .crypto import decrypt_file, NivoDecryptError
from .nivo_reader import NivoDB
from .mapping import ParmisChart, build_template, Mapping
from .merge import merge, MergeError


def _fmt(n): return f"{n:,.0f}"


def cmd_decrypt(a):
    decrypt_file(a.nivo, a.out)
    print(f"✅ رمزگشایی شد: {a.out}  (یک دیتابیس SQLite؛ با DB Browser for SQLite باز می‌شود)")


def cmd_inspect(a):
    with NivoDB(a.nivo) as n:
        tx = n.transactions()
        dates = sorted(t["RegFaDate"] for t in tx)
        print(f"نیوو: {len(tx)} تراکنش  |  از {dates[0]} تا {dates[-1]}  |  نسخه‌ی دیتابیس {n.user_version}")
        print(f"کیف پول‌ها: {[w['WalletName'] for w in n.wallets()]}")
        print(f"بانک‌ها: {[b['BankName'] for b in n.banks().values()]}")
        print("\nدسته‌ها (نوع | والد > نام | تعداد | جمع):")
        for k, c in sorted(n.categories().items(), key=lambda kv: (kv[0][0], -kv[1]["sum"])):
            print(f"  {k[0]:8} | {(k[1] + ' > ' if k[1] else '')}{k[2]} | {c['count']} | {_fmt(c['sum'])}")
        pairs = sum(1 for t in tx if t["MasterAccTransactionId"]) // 2
        print(f"\nجفت‌های انتقال: {pairs}   پروژه‌ها: {[p['ProjectName'] for p in n.projects().values()]}")
    if a.parmis:
        con = sqlite3.connect(a.parmis)
        ch = ParmisChart(con)
        print(f"\nپارمیس: نسخه‌ی دیتابیس {con.execute('pragma user_version').fetchone()[0]}"
              f" | {con.execute('select count(*) from Activity').fetchone()[0]} سند")
        print("حساب‌های نقد :", {c: ch.title(c) for c in ch.cash_candidates()})
        print("حساب‌های بانکی:", {c: ch.title(c) for c in ch.bank_candidates()})


def cmd_init(a):
    con = sqlite3.connect(a.parmis)
    chart = ParmisChart(con)
    with NivoDB(a.nivo) as n:
        t = build_template(n, chart)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2)
    miss = [k for k, v in t["banks"].items() if not v]
    print(f"✅ فایل نگاشت ساخته شد: {a.out}  ({len(t['categories'])} دسته)")
    if not t["cash_account"]: print("⚠️ cash_account را دستی پر کنید.")
    if miss: print("⚠️ این بانک‌ها را دستی به حساب پارمیس وصل کنید:", miss)
    print("بعد فایل را ویرایش کنید و با  --mapping  به دستور merge بدهید.")


def cmd_merge(a):
    mapping = Mapping.load(a.mapping) if a.mapping else None
    if a.cash_account:
        if mapping is None:
            con = sqlite3.connect(a.parmis)
            with NivoDB(a.nivo) as n:
                data = build_template(n, ParmisChart(con))
            mapping = Mapping(data)
        mapping.cash_account = a.cash_account
    import os, tempfile
    out = a.out
    if a.dry_run:
        fd, out = tempfile.mkstemp(suffix=".par"); os.close(fd)
    try:
        r = merge(a.nivo, a.parmis, out, mapping, tz=a.tz, multiplier=a.amount_multiplier,
                  allow_overlap=a.allow_overlap, keep_fiscal_start=a.keep_fiscal_start,
                  import_projects=not a.no_projects)
    finally:
        if a.dry_run and os.path.exists(out): os.remove(out)
    print(f"\n{'🧪 اجرای آزمایشی (فایلی نوشته نشد)' if a.dry_run else '✅ ادغام انجام شد'}")
    print(f"  تراکنش نیوو: {r['nivo_transactions']}  ->  سند جدید: {r['inserted']}"
          f"  (انتقال {r['transfers']}، اصلاحی {r['transfer_diff_rows']}، عادی {r['normal']})")
    print(f"  شماره‌ی اسناد جدید: {r['first_act_id']} تا {r['last_act_id']}   بازه‌ی تاریخ: {r['first_date']} تا {r['last_date']}")
    print(f"  حساب جدید: {len(r['new_accounts'])}   برچسب‌خورده: {r['tagged']}   ردشده: {r['skipped'] or 0}")
    print("  اثر ادغام بر موجودی حساب‌ها (به‌علاوه‌ی موجودی فعلی پارمیس):")
    for b in r["balance_effect"]:
        print(f"    {b['title']} ({b['account_id']}): {b['effect']:+,.0f}")
    for name, ok, detail in r["checks"]:
        print(f"  {'✔' if ok else '✘'} {name} {('— ' + detail) if detail else ''}")
    if a.report:
        r2 = {k: v for k, v in r.items()}
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(r2, f, ensure_ascii=False, indent=2)
        print(f"  گزارش کامل: {a.report}")
    if not a.dry_run:
        print(f"\nفایل خروجی: {a.out}\n⚠️ قبل از «بازیابی» در پارمیس حتماً از پارمیس فعلی خود پشتیبان بگیرید.")


def cmd_gui(a):
    from .gui import main as gui_main
    gui_main()


def build_parser():
    p = argparse.ArgumentParser(prog="nivo2parmis", description="ادغام پشتیبان نیوو در پشتیبان پارمیس")
    p.add_argument("--version", action="version", version=__version__)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("decrypt", help="رمزگشایی فایل .nivo به SQLite")
    s.add_argument("nivo"); s.add_argument("-o", "--out", required=True); s.set_defaults(fn=cmd_decrypt)
    s = sp.add_parser("inspect", help="نمایش محتوای فایل نیوو (و حساب‌های پارمیس)")
    s.add_argument("--nivo", required=True); s.add_argument("--parmis"); s.set_defaults(fn=cmd_inspect)
    s = sp.add_parser("init-mapping", help="ساخت فایل نگاشت پیشنهادی برای ویرایش")
    s.add_argument("--nivo", required=True); s.add_argument("--parmis", required=True)
    s.add_argument("-o", "--out", default="mapping.json"); s.set_defaults(fn=cmd_init)
    s = sp.add_parser("gui", help="پنجره‌ی گرافیکی ساده (یک‌کلیکی)")
    s.set_defaults(fn=cmd_gui)
    s = sp.add_parser("merge", help="ادغام و ساخت فایل نهایی .par")
    s.add_argument("--nivo", required=True); s.add_argument("--parmis", required=True)
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--mapping", help="فایل نگاشت (JSON). بدون آن، نگاشت خودکار استفاده می‌شود")
    s.add_argument("--cash-account", type=int, help="شناسه‌ی حساب نقد (کیف پول) در پارمیس")
    s.add_argument("--tz", default="Asia/Tehran", help="منطقه‌ی زمانی برای ساعت اسناد (پیش‌فرض: Asia/Tehran)")
    s.add_argument("--amount-multiplier", type=float, default=1.0,
                   help="ضریب مبلغ؛ مثلاً 10 اگر نیوو تومان و پارمیس ریال است (پیش‌فرض 1)")
    s.add_argument("--allow-overlap", action="store_true", help="اجازه‌ی هم‌پوشانی تاریخ با اسناد موجود پارمیس")
    s.add_argument("--keep-fiscal-start", action="store_true", help="تاریخ شروع سال مالی را تغییر نده")
    s.add_argument("--no-projects", action="store_true", help="پروژه‌های نیوو را به برچسب تبدیل نکن")
    s.add_argument("--dry-run", action="store_true", help="فقط اجرای آزمایشی و گزارش")
    s.add_argument("--report", help="مسیر فایل گزارش JSON")
    s.set_defaults(fn=cmd_merge)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        a.fn(a)
    except (MergeError, NivoDecryptError, FileNotFoundError, sqlite3.DatabaseError, ValueError) as e:
        print("❌ خطا:", e, file=sys.stderr)
        return 1
    return 0
