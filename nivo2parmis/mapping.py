"""نگاشت دسته‌بندی‌های نیوو به حساب‌های پارمیس.

هر تراکنش نیوو یک «دسته» دارد (مثلاً هزینه > غذا و نوشیدنی > میوه). در پارمیس هر
سند به یک «حساب پایانی» وصل می‌شود. این ماژول:

  * درخت حساب‌های پارمیس را می‌خواند (ParmisChart)
  * برای هر دسته‌ی نیوو یک پیشنهاد خودکار می‌سازد (propose)
  * نگاشت ویرایش‌شده‌ی کاربر (JSON) را می‌خواند و اعتبارسنجی می‌کند (Mapping)

انواع «هدف» (target) در فایل JSON:
  {"existing": 208}                               استفاده از حساب موجود (باید حساب پایانی باشد)
  {"under": 16, "title": "مسافرت"}                حساب پایانی با این عنوان زیر حساب ۱۶ (اگر نبود ساخته می‌شود)
  {"under_new_sub": {"root": 1, "title": "X"},    زیرگروه X زیر «هزینه‌ها» (یا «درآمدها») + حساب پایانی داخلش
   "title": "Y"}
"""
import json, re
from collections import defaultdict

ROOT_EXPENSE, ROOT_INCOME = 1, 2
ROOT_FOR_GROUP = {"expense": ROOT_EXPENSE, "income": ROOT_INCOME}


def norm(s) -> str:
    """نرمال‌سازی عنوان برای مقایسه: ی/ک عربی، نیم‌فاصله، فاصله‌های اضافه، حروف."""
    s = (s or "").replace("\u064a", "\u06cc").replace("\u0643", "\u06a9")
    s = s.replace("\u200c", " ").replace("\u200f", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


class ParmisChart:
    """درخت حساب‌های پارمیس (جدول accounts)."""

    def __init__(self, con):
        self.acc = {}
        for r in con.execute("select Ac_id,Ac_title,Ac_parent_id,Ac_isLeaf from accounts"):
            self.acc[r[0]] = {"id": r[0], "title": r[1] or "", "parent": r[2] or 0, "leaf": r[3] == 1}
        self.children = defaultdict(list)
        for a in self.acc.values():
            if a["parent"]:
                self.children[a["parent"]].append(a["id"])

    def chain(self, i):
        ch = [i]
        while self.acc[ch[-1]]["parent"]:
            ch.append(self.acc[ch[-1]]["parent"])
        return ch[::-1]                      # root ... i

    def depth(self, i): return len(self.chain(i)) - 1
    def root(self, i): return self.chain(i)[0]
    def title(self, i): return self.acc[i]["title"].strip()

    def path_text(self, i):
        return " > ".join(self.title(x) for x in self.chain(i))

    def find_postable(self, root, title):
        """حساب پایانی زیر root با همین عنوان؛ فقط اگر یکتا باشد."""
        t = norm(title)
        hits = [a["id"] for a in self.acc.values()
                if a["leaf"] and norm(a["title"]) == t and a["id"] != root and self.root(a["id"]) == root
                and self.depth(a["id"]) in (1, 2)]
        return hits[0] if len(hits) == 1 else None

    def find_sub(self, root, title):
        t = norm(title)
        hits = [c for c in self.children.get(root, []) if not self.acc[c]["leaf"] and norm(self.acc[c]["title"]) == t]
        return hits[0] if len(hits) == 1 else None

    def find_child(self, parent, title):
        t = norm(title)
        for c in self.children.get(parent, []):
            if self.acc[c]["leaf"] and norm(self.acc[c]["title"]) == t:
                return c
        return None

    def cash_candidates(self):
        return [c for c in self.children.get(3, []) if self.acc[c]["leaf"]]

    def bank_candidates(self):
        return [c for c in self.children.get(4, []) if self.acc[c]["leaf"]]


def propose(categories, chart: ParmisChart):
    """پیشنهاد خودکار هدف برای هر دسته‌ی نیوو. خروجی: فهرست دیکشنری‌های JSON-پذیر."""
    cats = sorted(categories.values(), key=lambda c: (c["group"], c["parent"], c["name"]))
    has_children = {(c["group"], norm(c["parent"])) for c in cats if c["parent"]}
    out = []
    for c in cats:
        root = ROOT_FOR_GROUP[c["group"]]
        name, parent = c["name"], c["parent"]
        note = None
        if not parent:
            hit = chart.find_postable(root, name)
            if hit:
                target = {"existing": hit}
                note = "هم‌نام با حساب موجود: " + chart.path_text(hit)
            elif (c["group"], norm(name)) in has_children:
                sub = chart.find_sub(root, name)
                target = ({"under": sub, "title": name + " (عمومی)"} if sub else
                          {"under_new_sub": {"root": root, "title": name}, "title": name + " (عمومی)"})
            else:
                target = {"under": root, "title": name}
        else:
            hit = chart.find_postable(root, name)
            p_hit = chart.find_postable(root, parent)
            if hit:
                target = {"existing": hit}
                note = "هم‌نام با حساب موجود: " + chart.path_text(hit)
            elif p_hit:   # والد با یک حساب پایانی موجود یکی شد؛ فرزند هم‌ردیف آن می‌شود
                up = chart.acc[p_hit]["parent"]
                target = {"under": up, "title": f"{parent} - {name}"}
            else:
                sub = chart.find_sub(root, parent)
                target = ({"under": sub, "title": name} if sub else
                          {"under_new_sub": {"root": root, "title": parent}, "title": name})
        item = {"group": c["group"], "parent": parent, "name": name, "count": c["count"],
                "sum": c["sum"], "target": target}
        if note:
            item["note"] = note
        out.append(item)
    return out


def propose_accounts(nivo_banks, nivo_wallets, chart: ParmisChart):
    """پیشنهاد کیف پول و بانک‌ها."""
    cash = None
    cands = chart.cash_candidates()
    names = [norm(w.get("WalletName")) for w in nivo_wallets] + ["کیف پول", "wallet"]
    for c in cands:
        if norm(chart.title(c)) in names:
            cash = c; break
    if cash is None and len(cands) == 1:
        cash = cands[0]
    banks = {}
    bcands = chart.bank_candidates()
    for b in nivo_banks.values():
        nm = norm(b.get("BankName"))
        nm = nm[len("بانک "):] if nm.startswith("بانک ") else nm
        hit = [c for c in bcands if nm and nm in norm(chart.title(c))]
        banks[b["BankName"]] = hit[0] if len(hit) == 1 else None
    return cash, banks


class MappingError(ValueError):
    pass


class Mapping:
    def __init__(self, data: dict):
        self.data = data
        self.cash_account = data.get("cash_account")
        self.banks = data.get("banks", {})
        self.by_key = {}
        for c in data.get("categories", []):
            self.by_key[(c["group"], norm(c["parent"]), norm(c["name"]))] = c["target"]

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def target_for(self, key):
        g, parent, name = key
        return self.by_key.get((g, norm(parent), norm(name)))

    def bank_account(self, bank_id, bank_name):
        for k in (bank_name, bank_id):
            if k in self.banks and self.banks[k]:
                return self.banks[k]
        for k, v in self.banks.items():
            if v and norm(k) == norm(bank_name):
                return v
        return None


def build_template(nivo, chart: ParmisChart):
    cats = nivo.categories()
    cash, banks = propose_accounts(nivo.banks(), nivo.wallets(), chart)
    used_banks = {b for b in (t["BankId"] for t in nivo.transactions()) if b}
    nb = nivo.banks()
    return {
        "version": 1,
        "_help": ("cash_account: شناسه‌ی حساب «کیف پول» در پارمیس. banks: نام بانک در نیوو -> شناسه‌ی حساب بانکی در پارمیس. "
                  "categories[].target را ویرایش کنید. راهنما: docs/mapping.md"),
        "cash_account": cash,
        "banks": {nb[b]["BankName"]: banks.get(nb[b]["BankName"]) for b in used_banks if b in nb},
        "categories": propose(cats, chart),
    }
