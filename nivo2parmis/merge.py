"""موتور ادغام: تراکنش‌های نیوو -> اسناد (Activity) پارمیس."""
import collections, datetime, os, shutil, sqlite3, zoneinfo
from .nivo_reader import NivoDB
from .mapping import ParmisChart, Mapping, propose, propose_accounts, ROOT_FOR_GROUP

TESTED_PARMIS_DB_VERSIONS = {12, 13}
CASH_ROOT, BANK_ROOT = 3, 4
REQUIRED_ACTIVITY_COLS = {
    "Act_rec_Subacc_id", "Act_rec_Root_id", "Act_pay_Subacc_id", "Act_pay_Root_id", "Act_iscash",
    "Act_isCheq_passed", "Act_cheq_id", "Act_set", "Act_accMember_id", "Act_info", "Act_amount",
    "Act_accPay_id", "Act_accRecive_id", "Act_date", "Act_ser", "Act_id", "Act_time", "Act_memberName",
    "Act_bankName", "PayPath", "RecivePath", "Act_attribute", "Act_Fiscal_id", "Act_multiId", "Act_multiType"}

INSERT_ACTIVITY = """insert into Activity (Act_rec_Subacc_id,Act_rec_Root_id,Act_pay_Subacc_id,Act_pay_Root_id,
    Act_iscash,Act_isCheq_passed,Act_cheq_id,Act_set,Act_accMember_id,Act_info,Act_amount,Act_accPay_id,
    Act_accRecive_id,Act_date,Act_ser,Act_id,Act_time,Act_memberName,Act_bankName,PayPath,RecivePath,
    Act_attribute,Act_Fiscal_id,Act_multiId,Act_multiType)
    values (?,?,?,?,1,-1,-1,?,-1,?,?,?,?,?,?,?,?,' ','',?,?,0,?,0,0)"""


class MergeError(RuntimeError):
    pass


class _Builder:
    """ساخت حساب‌های جدید در درخت پارمیس."""

    def __init__(self, con, chart):
        self.con, self.chart = con, chart
        self.next_id = con.execute("select max(Ac_id) from accounts").fetchone()[0] + 1
        self.rows, self.created = [], []

    def _create(self, parent, title, leaf):
        root = self.chart.root(parent)
        if root not in (1, 2):
            raise MergeError(f"حساب جدید فقط زیر «هزینه‌ها» یا «درآمدها» ساخته می‌شود (والد {parent})")
        d = self.chart.depth(parent)
        if d > 1 or (d == 1 and self.chart.acc[parent]["leaf"]):
            raise MergeError(f"زیر حساب {parent} ({self.chart.path_text(parent)}) نمی‌شود حساب ساخت؛ عمق/نوع نامعتبر.")
        if not leaf and d != 0:
            raise MergeError("زیرگروه فقط مستقیم زیر ریشه ساخته می‌شود")
        i = self.next_id; self.next_id += 1
        payable, recivable = (1, 0) if root == 1 else (0, 1)
        self.rows.append((None, -1, 0, 1 if leaf else 0, 0, payable, recivable, 0.0, "", title.strip(), i, parent,
                          "defaultpic", "", "", 0, "0"))
        self.chart.acc[i] = {"id": i, "title": title.strip(), "parent": parent, "leaf": leaf}
        self.chart.children[parent].append(i)
        self.created.append(i)
        return i

    def resolve(self, target):
        if "existing" in target:
            i = target["existing"]
            if i not in self.chart.acc:
                raise MergeError(f"حساب {i} در پارمیس وجود ندارد")
            if not self.chart.acc[i]["leaf"] or self.chart.depth(i) not in (1, 2):
                raise MergeError(f"حساب {i} ({self.chart.path_text(i)}) حساب پایانی نیست؛ سند روی آن ثبت نمی‌شود")
            return i
        title = target["title"]
        if "under_new_sub" in target:
            s = target["under_new_sub"]
            sub = self.chart.find_sub(s["root"], s["title"]) or self._create(s["root"], s["title"], False)
            parent = sub
        else:
            parent = target["under"]
            if parent not in self.chart.acc:
                raise MergeError(f"حساب والد {parent} در پارمیس نیست")
        return self.chart.find_child(parent, title) or self._create(parent, title, True)

    def flush(self):
        self.con.executemany("""insert into accounts (Ac_enable,Ac_bank_ac_id,Ac_isSystematic,Ac_isLeaf,Ac_isMember,
            Ac_payable,Ac_recivable,Ac_balance,Ac_info,Ac_title,Ac_id,Ac_parent_id,ac_icon,Ac_title_ar,Ac_title_en,
            Ac_pin,Ac_fav) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", self.rows)


def path_triple(chart, acc_id):
    ch = chart.chain(acc_id)
    return (ch[0], ch[1], -1) if len(ch) == 2 else (ch[0], ch[1], ch[2])


def merge(nivo_path, parmis_in, out_path, mapping=None, *, tz="Asia/Tehran", multiplier=1.0,
          allow_overlap=False, keep_fiscal_start=False, import_projects=True, run_verify=True, log=print):
    """mapping: Mapping | dict | None (None = پیشنهاد خودکار)."""
    tzinfo = zoneinfo.ZoneInfo(tz)
    nivo = NivoDB(nivo_path)
    if os.path.abspath(parmis_in) == os.path.abspath(out_path):
        raise MergeError("فایل خروجی نباید همان فایل ورودی پارمیس باشد")
    shutil.copyfile(parmis_in, out_path)
    con = sqlite3.connect(out_path)
    try:
        report = _run(nivo, con, parmis_in, out_path, mapping, tzinfo, multiplier, allow_overlap,
                      keep_fiscal_start, import_projects, log)
        con.commit()
        con.close()
        if run_verify:
            from .verify import verify
            checks = verify(parmis_in, out_path, nivo, report, multiplier)
            report["checks"] = checks
            bad = [c for c in checks if not c[1]]
            if bad:
                raise MergeError("اعتبارسنجی نهایی ناموفق بود: " + "; ".join(f"{c[0]} ({c[2]})" for c in bad))
        return report
    except Exception:
        try: con.close()
        except Exception: pass
        if os.path.exists(out_path):
            os.remove(out_path)
        raise
    finally:
        nivo.close()


def _run(nivo, con, parmis_in, out_path, mapping, tzinfo, mult, allow_overlap, keep_fiscal, do_projects, log):
    uv = con.execute("pragma user_version").fetchone()[0]
    if uv not in TESTED_PARMIS_DB_VERSIONS:
        log(f"⚠️ نسخه‌ی دیتابیس پارمیس {uv} است؛ ابزار فقط با نسخه‌های {sorted(TESTED_PARMIS_DB_VERSIONS)} تست شده.")
    cols = {r[1] for r in con.execute("pragma table_info(Activity)")}
    if REQUIRED_ACTIVITY_COLS - cols:
        raise MergeError("ستون‌های جدول Activity پارمیس مطابق انتظار نیست: " + ", ".join(sorted(REQUIRED_ACTIVITY_COLS - cols)))
    chart = ParmisChart(con)
    builder = _Builder(con, chart)

    wallets = nivo.wallets()
    if len(wallets) > 1:
        log(f"⚠️ نیوو {len(wallets)} کیف پول دارد؛ همه‌ی تراکنش‌های نقد به یک حساب نقد پارمیس می‌روند.")
    banks, accs = nivo.banks(), nivo.accounts()
    txs = nivo.transactions()
    if not txs:
        raise MergeError("فایل نیوو هیچ تراکنشی ندارد")

    # ---- نگاشت ----
    cats = nivo.categories()
    if mapping is None:
        auto_cash, auto_banks = propose_accounts(banks, wallets, chart)
        mapping = Mapping({"cash_account": auto_cash, "banks": auto_banks, "categories": propose(cats, chart)})
    elif isinstance(mapping, dict):
        mapping = Mapping(mapping)
    cash = mapping.cash_account
    if not cash:
        raise MergeError("حساب نقد (cash_account) مشخص نیست. شناسه‌ی «کیف پول» پارمیس را در فایل نگاشت یا با --cash-account بدهید. "
                         "(نامزدها: " + "، ".join(f"{c}={chart.title(c)}" for c in chart.cash_candidates()) + ")")
    if cash not in chart.acc or chart.root(cash) != CASH_ROOT:
        raise MergeError(f"cash_account={cash} زیر «صندوق‌ها» نیست")
    fallback_auto = Mapping({"categories": propose(cats, chart)})

    def bank_acc(t):
        b = banks.get(t["BankId"])
        name = b["BankName"] if b else t["BankId"]
        a = mapping.bank_account(t["BankId"], name)
        if not a:
            raise MergeError(f"بانک «{name}» به حساب بانکی پارمیس نگاشت نشده؛ در فایل نگاشت بخش banks را کامل کنید. "
                             "(نامزدها: " + "، ".join(f"{c}={chart.title(c)}" for c in chart.bank_candidates()) + ")")
        if a not in chart.acc or chart.root(a) != BANK_ROOT:
            raise MergeError(f"حساب بانکی {a} زیر «بانک‌ها» نیست")
        return a

    def source(t):
        if t["BankId"]:
            return bank_acc(t)
        if t["AccountId"] not in accs:   # بدون دسته و بدون بانک: اگر در یادداشت اسم بانک آمده، همان بانک
            for bid, b in banks.items():
                if b.get("BankName") and b["BankName"] in (t["Note"] or ""):
                    return mapping.bank_account(bid, b["BankName"]) or cash
        return cash

    by_id = {t["AccTransactionId"]: t for t in txs}
    last_nivo = max(t["RegFaDate"] for t in txs)
    first_nivo = min(t["RegFaDate"] for t in txs)
    ov = con.execute("select count(*) from Activity where Act_date<=?", (last_nivo,)).fetchone()[0]
    if ov and not allow_overlap:
        raise MergeError(f"پارمیس {ov} سند با تاریخ ≤ {last_nivo} دارد (آخرین تاریخ نیوو). "
                         "اگر قبلاً ادغام کرده‌اید دوباره نکنید؛ در غیر این صورت با --allow-overlap ادامه دهید (احتمال سند تکراری).")

    ops, used, skipped = [], set(), collections.Counter()
    usage = collections.OrderedDict()
    # ---- جفت‌های انتقال ----
    for r in txs:
        mid = r["MasterAccTransactionId"]
        if not mid or r["AccTransactionId"] in used or mid not in by_id:
            continue
        o = by_id[mid]
        neg, pos = (r, o) if r["Amount"] < 0 else (o, r)
        if not (neg["Amount"] < 0 < pos["Amount"]) or o["MasterAccTransactionId"] != r["AccTransactionId"]:
            continue
        src, dst = source(neg), source(pos)
        if src == dst:
            raise MergeError(f"انتقال {r['RegFaDate']} بین یک حساب (مبدأ و مقصد یکی‌اند)؛ احتمالاً بانک‌ها درست نگاشت نشده‌اند")
        used |= {r["AccTransactionId"], o["AccTransactionId"]}
        first = min((neg, pos), key=lambda x: x["RegGeDate"])
        note = neg["Note"] or pos["Note"] or ""
        ops.append(((r["RegFaDate"], first["RegGeDate"], 0), dict(
            kind="transfer", set=2, date=r["RegFaDate"], ms=first["RegGeDate"], amount=-neg["Amount"] * mult,
            note=note, debit=dst, credit=src)))
        diff = pos["Amount"] + neg["Amount"]
        if diff:
            g = "income" if diff > 0 else "expense"
            ops.append(((r["RegFaDate"], first["RegGeDate"], 1), dict(
                kind="diff", set=0 if diff > 0 else 1, date=r["RegFaDate"], ms=first["RegGeDate"], amount=abs(diff) * mult,
                note="مابه‌التفاوت دو سمت انتقال (نیوو): " + note,
                cat=builder.resolve({"under": ROOT_FOR_GROUP[g], "title": "مابه‌التفاوت انتقال (نیوو)"}),
                acct=dst)))
    # ---- بقیه ----
    for t in txs:
        if t["AccTransactionId"] in used:
            continue
        if t["Amount"] == 0:
            skipped["zero_amount"] += 1
            continue
        key = nivo.category_key(t, accs)
        tgt = mapping.target_for(key) or fallback_auto.target_for(key)
        if tgt is None:
            raise MergeError(f"برای دسته‌ی {key} نگاشتی پیدا نشد")
        cat = builder.resolve(tgt)
        u = usage.setdefault(key, {"group": key[0], "parent": key[1], "name": key[2], "count": 0, "sum": 0, "account_id": cat})
        u["count"] += 1; u["sum"] += abs(t["Amount"])
        ops.append(((t["RegFaDate"], t["RegGeDate"], 2), dict(
            kind="normal", set=0 if t["Amount"] > 0 else 1, date=t["RegFaDate"], ms=t["RegGeDate"],
            amount=abs(t["Amount"]) * mult, note=t["Note"] or "", cat=cat, acct=source(t),
            project=t["ProjectId"] if do_projects else "")))
    ops.sort(key=lambda x: x[0])

    # ---- سال مالی ----
    fy = con.execute("select fiscal_id,fiscal_beginDate from FiscalYear where fiscal_status=1 order by fiscal_id").fetchone() \
        or con.execute("select fiscal_id,fiscal_beginDate from FiscalYear order by fiscal_id").fetchone()
    if not fy:
        raise MergeError("جدول FiscalYear پارمیس خالی است")
    fy_id = fy[0]

    builder.flush()
    # ---- برچسب پروژه ----
    projects = nivo.projects()
    tag_of = {}
    if do_projects:
        for pid in dict.fromkeys(o["project"] for _, o in ops if o.get("project")):   # به ترتیب اولین ظهور (قطعی)
            name = (projects.get(pid) or {}).get("ProjectName", "").strip()
            if not name:
                continue
            ex = con.execute("select TagId from Tag where Name=? and TagTypeId=3", (name,)).fetchone()
            if ex:
                tag_of[pid] = ex[0]
            else:
                tid = (con.execute("select max(TagId) from Tag").fetchone()[0] or 0) + 1
                con.execute("insert into Tag (TagId,Name,TagTypeId,Icon,Info) values (?,?,3,'defaultpic','')", (tid, name))
                tag_of[pid] = tid
    next_ta = (con.execute("select max(TagActivityId) from TagActivity").fetchone()[0] or 0) + 1

    # ---- درج اسناد ----
    next_id = con.execute("select max(Act_id) from Activity").fetchone()[0] or 0
    next_id += 1
    first_id = next_id
    tagged = 0
    effect = collections.defaultdict(float)          # اثر اسناد جدید بر موجودی حساب‌های نقد/بانک
    for _, o in ops:
        if o["kind"] == "transfer":
            debit, credit = o["debit"], o["credit"]
        elif o["set"] == 1:
            debit, credit = o["cat"], o["acct"]
        else:
            debit, credit = o["acct"], o["cat"]
        pp, rp = path_triple(chart, debit), path_triple(chart, credit)
        if pp[0] in (CASH_ROOT, BANK_ROOT): effect[pp[1]] += o["amount"]
        if rp[0] in (CASH_ROOT, BANK_ROOT): effect[rp[1]] -= o["amount"]
        hhmm = datetime.datetime.fromtimestamp(o["ms"] / 1000, tzinfo).strftime("%H:%M")
        con.execute(INSERT_ACTIVITY, (rp[1], rp[0], pp[1], pp[0], o["set"], o["note"], float(o["amount"]), pp[2], rp[2],
                                      o["date"], next_id, next_id, hhmm, ",".join(map(str, pp)), ",".join(map(str, rp)), fy_id))
        if o.get("project") in tag_of:
            con.execute("insert into TagActivity (TagActivityId,TagId,ActivityId,PatternId) values (?,?,?,-1)",
                        (next_ta, tag_of[o["project"]], next_id))
            next_ta += 1; tagged += 1
        next_id += 1
    if not keep_fiscal and fy[1] and fy[1] > first_nivo:
        con.execute("update FiscalYear set fiscal_beginDate=? where fiscal_id=?", (first_nivo, fy_id))

    kinds = collections.Counter(o["kind"] for _, o in ops)
    return {
        "nivo_transactions": len(txs), "inserted": len(ops), "first_act_id": first_id, "last_act_id": next_id - 1,
        "transfers": kinds["transfer"], "transfer_diff_rows": kinds["diff"], "normal": kinds["normal"],
        "skipped": dict(skipped), "tagged": tagged, "fiscal_id": fy_id, "first_date": first_nivo, "last_date": last_nivo,
        "new_accounts": [{"id": i, "path": chart.path_text(i)} for i in builder.created],
        "category_usage": [dict(v, path=chart.path_text(v["account_id"])) for v in usage.values()],
        "cash_account": cash, "banks": mapping.banks, "multiplier": mult,
        "balance_effect": [{"account_id": i, "title": chart.title(i), "effect": e} for i, e in sorted(effect.items())],
    }
