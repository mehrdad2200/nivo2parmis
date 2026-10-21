"""خواندن دیتابیس نیوو (فایل .nivo رمزشده یا SQLite رمزگشایی‌شده)."""
import os, sqlite3, tempfile
from .crypto import decrypt_file

GROUPS = {1: "income", 2: "expense"}


class NivoDB:
    def __init__(self, path: str):
        self._tmp = None
        with open(path, "rb") as f:
            head = f.read(15)
        if head != b"SQLite format 3":
            fd, self._tmp = tempfile.mkstemp(suffix=".sqlite")
            os.close(fd)
            decrypt_file(path, self._tmp)
            path = self._tmp
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.user_version = self.con.execute("pragma user_version").fetchone()[0]
        tables = {r[0] for r in self.con.execute("select name from sqlite_master where type='table'")}
        if "AccTransaction" not in tables:
            self.close()
            hint = " (به نظر فایل پارمیس است؛ آیا --nivo و --parmis را جابه‌جا داده‌اید؟)" if "Activity" in tables else ""
            raise ValueError("این فایل پشتیبان نیوو نیست: جدول AccTransaction ندارد" + hint)

    def close(self):
        self.con.close()
        if self._tmp and os.path.exists(self._tmp):
            os.remove(self._tmp)

    def __enter__(self): return self
    def __exit__(self, *a): self.close()

    def wallets(self):
        return [dict(r) for r in self.con.execute("select * from Wallet")]

    def banks(self):
        return {r["BankId"]: dict(r) for r in self.con.execute("select * from Bank")}

    def accounts(self):
        return {r["AccountId"]: dict(r) for r in self.con.execute("select * from Account")}

    def projects(self):
        return {r["ProjectId"]: dict(r) for r in self.con.execute("select * from Project")}

    def transactions(self):
        return [dict(r) for r in self.con.execute("select * from AccTransaction")]

    def category_key(self, row, accounts=None):
        """(group, parent_name, name) یک تراکنش. group: income | expense."""
        accounts = accounts if accounts is not None else self.accounts()
        a = accounts.get(row["AccountId"])
        if not a:  # دسته‌ی حذف‌شده/خالی (مثلاً تراکنش واردشده از پیامک)
            g = GROUPS.get(row["AccountGroupId"]) or ("income" if row["Amount"] > 0 else "expense")
            return (g, "", "نامشخص")
        par = accounts.get(a["ParentAccountId"])
        return (GROUPS[a["GroupId"]], (par["AccountName"].strip() if par else ""), a["AccountName"].strip())

    def categories(self):
        """دسته‌های واقعاً استفاده‌شده + تعداد و جمع مبلغ (بدون جفت‌های انتقال)."""
        accs = self.accounts()
        out = {}
        for r in self.transactions():
            if r["MasterAccTransactionId"]:
                continue
            k = self.category_key(r, accs)
            d = out.setdefault(k, {"group": k[0], "parent": k[1], "name": k[2], "count": 0, "sum": 0})
            d["count"] += 1
            d["sum"] += abs(r["Amount"])
        return out
