#!/usr/bin/env python3
"""ساخت داده‌ی نمونه‌ی *ساختگی* (بدون هیچ اطلاعات واقعی) برای تست و آزمایش ابزار.

    python examples/make_example_data.py            # فایل‌ها را کنار همین اسکریپت می‌سازد

خروجی:
    sample_nivo.nivo      پشتیبان نیوو (رمزشده، مثل فایل واقعی)
    sample_parmis.par     پشتیبان پارمیس با چند سند (ماه‌های بعد از نیوو)
"""
import os, random, shutil, sqlite3, sys, datetime, zoneinfo
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from nivo2parmis.crypto import encrypt_bytes

TZ = zoneinfo.ZoneInfo("Asia/Tehran")


def _ms(fa_date, hh=12, mm=0):
    import jdatetime
    y, m, d = map(int, fa_date.split("/"))
    g = jdatetime.date(y, m, d).togregorian()
    return int(datetime.datetime(g.year, g.month, g.day, hh, mm, tzinfo=TZ).timestamp() * 1000)


def build_nivo_sqlite(path, seed=7):
    rnd = random.Random(seed)
    if os.path.exists(path): os.remove(path)
    con = sqlite3.connect(path)
    con.executescript(open(os.path.join(os.path.dirname(HERE), "tests", "nivo_schema.sql"), encoding="utf-8").read())
    con.execute("pragma user_version=18")
    W = "w1"
    con.execute("insert into Wallet (WalletId,WalletName,CurrencyTypeId) values (?,?,2)", (W, "کیف پول"))
    con.execute("insert into Bank (BankId,BankName,WalletId,CreatedAt) values ('b1','بانک نمونه','w1',1)")
    con.execute("insert into Project (ProjectId,ProjectName,WalletId,CreatedAt) values ('p1','سفر شمال','w1',1)")
    A = {}
    def acc(key, name, group, parent="", pre="0"):
        A[key] = key
        con.execute("insert into Account (AccountId,AccountName,GroupId,ParentAccountId,PredefinedType,IsLocked,CreationOrder,WalletId) "
                    "values (?,?,?,?,?,0,0,?)", (key, name, group, A.get(parent, ""), pre, W))
    acc("i_salary", "حقوق", 1); acc("i_sale", "فروش", 1); acc("i_sale_web", "فروش اینترنتی", 1, "i_sale")
    acc("i_other", "سایر", 1, pre="103"); acc("i_t", "جیب به جیب", 1, pre="104")
    acc("e_family", "خانواده", 2); acc("e_food", "غذا و نوشیدنی", 2); acc("e_fruit", "میوه", 2, "e_food")
    acc("e_transport", "حمل و نقل", 2); acc("e_lend", "قرض دادن", 2, pre="201"); acc("e_t", "جیب به جیب", 2, pre="206")
    n = [0]
    def tx(date, acc_key, amount, note="", bank="", hh=12, mm=0, project="", master=""):
        n[0] += 1
        a = con.execute("select AccountName,GroupId from Account where AccountId=?", (acc_key,)).fetchone() if acc_key else ("", 1 if amount > 0 else 2)
        tid = f"t{n[0]:04d}"
        con.execute("insert into AccTransaction (AccTransactionId,AccountId,AccountName,AccountGroupId,RegFaDate,RegGeDate,Note,Amount,"
                    "BankId,ProjectId,ProjectName,MasterAccTransactionId,WalletId,Tag,GeneralReferenceId) values (?,?,?,?,?,?,?,?,?,?,?,?,?,'','')",
                    (tid, acc_key, a[0], a[1], date, _ms(date, hh, mm), note, amount, bank, project,
                     "سفر شمال" if project else "", master, W))
        return tid
    for m in range(1, 7):                                   # ۶ ماه تراکنش‌های عادی
        tx(f"1401/{m:02d}/01", "i_salary", 20_000_000, "حقوق ماه " + "۱۲۳۴۵۶"[m - 1], "b1", 9, 30)
        for d in (3, 9, 15, 21, 27):
            tx(f"1401/{m:02d}/{d:02d}", "e_transport", -rnd.choice([12000, 24000, 31700]), "مترو", "" , 8, 15)
            tx(f"1401/{m:02d}/{d:02d}", "e_food", -rnd.randrange(40, 400) * 1000, "ناهار", "b1", 13, 40)
        tx(f"1401/{m:02d}/12", "e_fruit", -rnd.randrange(50, 150) * 1000, "میوه")
        tx(f"1401/{m:02d}/20", "e_family", -2_000_000, "کمک به خانواده", "b1")
    tx("1401/03/10", "i_sale_web", 3_500_000, "فروش یک وسیله", "b1")
    tx("1401/04/02", "e_lend", -1_000_000, "قرض به دوست")
    tx("1401/05/02", "i_other", 1_000_000, "برگشت قرض", "")
    tx("1401/06/05", "e_transport", -150_000, "کرایه سفر #شمال", "", project="p1")
    tx("1401/06/06", "e_food", -420_000, "رستوران سفر", "b1", project="p1")
    # انتقال بین نقد و بانک (دو جفت: یکی مساوی، یکی با ۵٬۶۰۰ تومان اختلاف)
    a = tx("1401/02/15", "e_t", -2_000_000, "برداشت از بانک", "b1")
    b = tx("1401/02/15", "i_t", 2_000_000, "برداشت از بانک", "", master=a)
    con.execute("update AccTransaction set MasterAccTransactionId=? where AccTransactionId=?", (b, a))
    a = tx("1401/05/20", "e_t", -594_400, "واریز به بانک", "")
    b = tx("1401/05/20", "i_t", 600_000, "واریز به بانک", "b1", master=a)
    con.execute("update AccTransaction set MasterAccTransactionId=? where AccTransactionId=?", (b, a))
    # تراکنش بدون دسته (وارد شده از پیامک)
    tx("1401/06/10", None, -85_000, "بانک نمونه - برداشت")
    con.commit(); con.close()


def build(outdir=HERE):
    tmp = os.path.join(outdir, "_tmp_nivo.sqlite")
    build_nivo_sqlite(tmp)
    with open(tmp, "rb") as f, open(os.path.join(outdir, "sample_nivo.nivo"), "wb") as g:
        g.write(encrypt_bytes(f.read()))
    os.remove(tmp)
    dst = os.path.join(outdir, "sample_parmis.par")
    shutil.copyfile(os.path.join(HERE, "parmis_template.par"), dst)
    c = sqlite3.connect(dst)
    ins = ("insert into Activity (Act_rec_Subacc_id,Act_rec_Root_id,Act_pay_Subacc_id,Act_pay_Root_id,Act_iscash,Act_isCheq_passed,Act_cheq_id,"
           "Act_set,Act_accMember_id,Act_info,Act_amount,Act_accPay_id,Act_accRecive_id,Act_date,Act_ser,Act_id,Act_time,Act_memberName,Act_bankName,"
           "PayPath,RecivePath,Act_attribute,Act_Fiscal_id,Act_multiId,Act_multiType) values (152,3,174,1,1,-1,-1,1,-1,?,?,-1,-1,?,?,?,'10:00',' ','','1,174,-1','3,152,-1',0,1,0,0)")
    for i, (d, amt, note) in enumerate([("1402/07/02", 500_000, "نمونه ۱"), ("1402/07/09", 250_000, "نمونه ۲"), ("1402/07/15", 1_200_000, "نمونه ۳")], 1):
        c.execute(ins, (note, amt, d, i, i))
    c.commit(); c.close()
    return os.path.join(outdir, "sample_nivo.nivo"), dst


if __name__ == "__main__":
    print(*build(sys.argv[1] if len(sys.argv) > 1 else HERE), sep="\n")
