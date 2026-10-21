"""اعتبارسنجی خروجی ادغام (بعد از هر ادغام خودکار اجرا می‌شود)."""
import collections, sqlite3
from .mapping import ParmisChart

MODIFIED_TABLES = {"Activity", "accounts", "Tag", "TagActivity", "FiscalYear"}


def verify(orig_path, out_path, nivo, report, multiplier=1.0):
    o, n = sqlite3.connect(orig_path), sqlite3.connect(out_path)
    o.row_factory = n.row_factory = sqlite3.Row
    res = []
    add = lambda name, ok, detail="": res.append((name, bool(ok), detail))

    add("integrity_check", n.execute("pragma integrity_check").fetchone()[0] == "ok")
    add("user_version بدون تغییر", n.execute("pragma user_version").fetchone()[0] == o.execute("pragma user_version").fetchone()[0])
    add("journal_mode=delete (فایل تک‌تکه)", n.execute("pragma journal_mode").fetchone()[0] == "delete")
    so = sorted(map(tuple, o.execute("select name,sql from sqlite_master")))
    sn = sorted(map(tuple, n.execute("select name,sql from sqlite_master")))
    add("ساختار دیتابیس بدون تغییر", so == sn)

    # جدول‌های دست‌نخورده
    changed = []
    for (t,) in o.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"):
        if t in MODIFIED_TABLES:
            continue
        if [tuple(r) for r in o.execute(f'select * from "{t}"')] != [tuple(r) for r in n.execute(f'select * from "{t}"')]:
            changed.append(t)
    add("جدول‌های دیگر دست‌نخورده‌اند", not changed, ",".join(changed))

    last_old = o.execute("select coalesce(max(Act_id),0) from Activity").fetchone()[0]
    old = [tuple(r) for r in o.execute("select * from Activity order by Act_id")]
    cur = [tuple(r) for r in n.execute("select * from Activity where Act_id<=? order by Act_id", (last_old,))]
    add("همه‌ی اسناد قبلی پارمیس بدون تغییرند", old == cur, f"{len(old)} سند")
    add("حساب‌های قبلی بدون تغییرند",
        {tuple(r) for r in o.execute("select * from accounts")} <= {tuple(r) for r in n.execute("select * from accounts")})

    new = n.execute("select * from Activity where Act_id>? order by Act_id", (last_old,)).fetchall()
    add("تعداد اسناد جدید", len(new) == report["inserted"], f"{len(new)} / {report['inserted']}")
    chart = ParmisChart(n)
    bad = collections.Counter()
    for r in new:
        if r["Act_ser"] != r["Act_id"]: bad["ser!=id"] += 1
        if not r["Act_amount"] > 0: bad["amount<=0"] += 1
        for side in ("Pay", "Recive"):
            root = r["Act_pay_Root_id" if side == "Pay" else "Act_rec_Root_id"]
            sub = r["Act_pay_Subacc_id" if side == "Pay" else "Act_rec_Subacc_id"]
            leaf = r["Act_accPay_id" if side == "Pay" else "Act_accRecive_id"]
            if [int(x) for x in r[side + "Path"].split(",")] != [root, sub, leaf]: bad["path"] += 1
            term = leaf if leaf > 0 else sub
            if term not in chart.acc: bad["missing_account"] += 1; continue
            if not chart.acc[term]["leaf"]: bad["non_leaf"] += 1
            exp = [root, sub] if leaf <= 0 else [root, sub, leaf]
            if chart.chain(term) != exp: bad["chain"] += 1
        if r["Act_set"] == 1 and r["Act_pay_Root_id"] != 1: bad["expense_root"] += 1
        if r["Act_set"] == 0 and r["Act_rec_Root_id"] != 2: bad["income_root"] += 1
    add("ساختار تک‌تک اسناد جدید (مسیر، حساب پایانی، جهت)", not bad, str(dict(bad)))

    # تطبیق ردیف‌به‌ردیف تراکنش‌های غیر انتقال
    paired = _paired_ids(nivo.transactions())
    A = collections.Counter((t["RegFaDate"], round(abs(t["Amount"]) * multiplier, 6), t["Note"] or "", t["Amount"] > 0)
                            for t in nivo.transactions() if t["AccTransactionId"] not in paired and t["Amount"] != 0)
    B = collections.Counter((r["Act_date"], round(r["Act_amount"], 6), r["Act_info"], r["Act_set"] == 0)
                            for r in new if r["Act_set"] in (0, 1) and not r["Act_info"].startswith("مابه‌التفاوت دو سمت"))
    add("هر تراکنش نیوو دقیقاً یک‌بار (تاریخ/مبلغ/یادداشت/جهت)", A == B, f"{sum(A.values())} ردیف")

    # اثر خالص بر موجودی‌ها = خالص نیوو
    def eff():
        d = sum(r["Act_amount"] for r in new if r["Act_pay_Root_id"] in (3, 4))
        c = sum(r["Act_amount"] for r in new if r["Act_rec_Root_id"] in (3, 4))
        return d - c
    nivo_net = sum(t["Amount"] for t in nivo.transactions()) * multiplier
    add("اثر خالص روی موجودی نقد+بانک = خالص نیوو", abs(eff() - nivo_net) < 1e-6, f"{eff():,.0f} / {nivo_net:,.0f}")
    return res


def _paired_ids(txs):
    by = {t["AccTransactionId"]: t for t in txs}
    out = set()
    for t in txs:
        m = t["MasterAccTransactionId"]
        if m and m in by and by[m]["MasterAccTransactionId"] == t["AccTransactionId"]:
            a, b = t["Amount"], by[m]["Amount"]
            if (a < 0 < b) or (b < 0 < a):
                out |= {t["AccTransactionId"], m}
    return out
