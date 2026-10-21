import json, os, sqlite3
import pytest
from nivo2parmis.merge import merge, MergeError
from nivo2parmis.mapping import Mapping
from nivo2parmis.cli import main


def rows(path, sql, *a):
    c = sqlite3.connect(path); c.row_factory = sqlite3.Row
    return c.execute(sql, a).fetchall()


@pytest.fixture()
def merged(sample, tmp_path):
    nivo, parmis = sample
    out = str(tmp_path / "out.par")
    rep = merge(nivo, parmis, out, log=lambda *a: None)
    return out, rep, parmis


def test_counts_and_checks(merged):
    out, rep, parmis = merged
    assert rep["nivo_transactions"] == 88
    assert rep["inserted"] == 87              # 88 - 4 (دو جفت انتقال) + 2 انتقال + 1 اصلاحی
    assert rep["transfers"] == 2 and rep["transfer_diff_rows"] == 1
    assert all(ok for _, ok, _ in rep["checks"]), rep["checks"]
    assert rows(out, "select count(*) c from Activity")[0]["c"] == 3 + 87


def test_existing_rows_untouched_and_appended_after(merged):
    out, rep, parmis = merged
    old = [tuple(r) for r in rows(parmis, "select * from Activity order by Act_id")]
    new = [tuple(r) for r in rows(out, "select * from Activity where Act_id<=3 order by Act_id")]
    assert old == new
    assert rep["first_act_id"] == 4 and rep["last_act_id"] == 90
    dates = [r["Act_date"] for r in rows(out, "select Act_date from Activity where Act_id>=4 order by Act_id")]
    assert dates == sorted(dates)


def test_transfer_and_difference(merged):
    out, *_ = merged
    t = rows(out, "select * from Activity where Act_set=2 order by Act_date")
    assert len(t) == 2
    # برداشت از بانک: بانک(173) بستانکار، کیف پول(152) بدهکار
    assert (t[0]["Act_pay_Subacc_id"], t[0]["Act_rec_Subacc_id"], t[0]["Act_amount"]) == (152, 173, 2_000_000)
    assert (t[1]["Act_pay_Subacc_id"], t[1]["Act_rec_Subacc_id"], t[1]["Act_amount"]) == (173, 152, 594_400)
    d = rows(out, "select * from Activity where Act_info like 'مابه‌التفاوت%'")
    assert len(d) == 1 and d[0]["Act_amount"] == 5_600 and d[0]["Act_set"] == 0


def test_existing_account_reused_and_new_sub_created(merged):
    out, rep, _ = merged
    fam = rows(out, "select count(*) c from Activity where Act_pay_Subacc_id=174")[0]["c"]
    assert fam == 3 + 6                       # ۳ سند نمونه‌ی پارمیس + ۶ تراکنش «خانواده»
    paths = {a["path"] for a in rep["new_accounts"]}
    assert "هزینه ها > غذا و نوشیدنی > میوه" in paths
    assert "هزینه ها > غذا و نوشیدنی > غذا و نوشیدنی (عمومی)" in paths


def test_time_and_persian_note_preserved(merged):
    out, *_ = merged
    r = rows(out, "select * from Activity where Act_info='حقوق ماه ۱' ")[0]
    assert r["Act_time"] == "09:30" and r["Act_date"] == "1401/01/01"


def test_project_becomes_tag(merged):
    out, rep, _ = merged
    assert rep["tagged"] == 2
    t = rows(out, "select t.Name,t.TagTypeId,count(*) n from TagActivity ta join Tag t using(TagId) group by 1,2")
    assert [(r["Name"], r["TagTypeId"], r["n"]) for r in t] == [("سفر شمال", 3, 2)]


def test_fiscal_start_moved(merged):
    out, *_ = merged
    assert rows(out, "select fiscal_beginDate b from FiscalYear")[0]["b"] == "1401/01/01"


def test_cannot_merge_twice(merged, sample, tmp_path):
    out, *_ = merged
    with pytest.raises(MergeError, match="سند با تاریخ"):
        merge(sample[0], out, str(tmp_path / "again.par"), log=lambda *a: None)
    assert not (tmp_path / "again.par").exists()


def test_unmapped_bank_is_error_and_output_removed(sample, tmp_path):
    nivo, parmis = sample
    mp = {"cash_account": 152, "banks": {}, "categories": []}
    with pytest.raises(MergeError, match="بانک"):
        merge(nivo, parmis, str(tmp_path / "x.par"), mp, log=lambda *a: None)
    assert not (tmp_path / "x.par").exists()


def test_custom_mapping_override(sample, tmp_path):
    nivo, parmis = sample
    mp = {"cash_account": 152, "banks": {"بانک نمونه": 173},
          "categories": [{"group": "expense", "parent": "", "name": "حمل و نقل", "target": {"under": 16, "title": "مترو و اتوبوس"}}]}
    out = str(tmp_path / "o.par")
    rep = merge(nivo, parmis, out, mp, log=lambda *a: None)
    r = rows(out, "select PayPath from Activity where Act_info='مترو' limit 1")[0]
    assert r["PayPath"].startswith("1,16,")            # زیر «ایاب و ذهاب» ساخته شد
    assert any(a["path"].endswith("ایاب و ذهاب و مسافرت > مترو و اتوبوس") for a in rep["new_accounts"])


def test_amount_multiplier(sample, tmp_path):
    nivo, parmis = sample
    out = str(tmp_path / "m.par")
    merge(nivo, parmis, out, multiplier=10, log=lambda *a: None)
    assert rows(out, "select Act_amount a from Activity where Act_info='کمک به خانواده' limit 1")[0]["a"] == 20_000_000


def test_failed_verification_removes_output(sample, tmp_path, monkeypatch):
    import nivo2parmis.verify as v
    monkeypatch.setattr(v, "verify", lambda *a, **k: [("x", False, "boom")])
    with pytest.raises(MergeError, match="اعتبارسنجی"):
        merge(sample[0], sample[1], str(tmp_path / "f.par"), log=lambda *a: None)
    assert not (tmp_path / "f.par").exists()


def test_cli_dry_run_writes_nothing(sample, tmp_path, capsys):
    out = tmp_path / "dry.par"
    rc = main(["merge", "--nivo", sample[0], "--parmis", sample[1], "-o", str(out), "--dry-run"])
    assert rc == 0 and not out.exists()
    assert "اجرای آزمایشی" in capsys.readouterr().out


def test_cli_init_mapping_roundtrip(sample, tmp_path):
    mp = tmp_path / "m.json"
    assert main(["init-mapping", "--nivo", sample[0], "--parmis", sample[1], "-o", str(mp)]) == 0
    data = json.load(open(mp, encoding="utf-8"))
    assert data["cash_account"] == 152 and data["banks"] == {"بانک نمونه": 173}
    out = tmp_path / "o.par"
    assert main(["merge", "--nivo", sample[0], "--parmis", sample[1], "-o", str(out), "--mapping", str(mp)]) == 0
    assert out.exists()


def test_output_is_deterministic_across_hash_seeds(sample, tmp_path):
    """ترتیب ساخت برچسب/حساب نباید به seed تصادفی پایتون وابسته باشد."""
    import hashlib, subprocess, sys
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    digests = set()
    for seed in ("1", "2", "3"):
        out = tmp_path / f"d{seed}.par"
        subprocess.run([sys.executable, "-m", "nivo2parmis", "merge", "--nivo", sample[0], "--parmis", sample[1], "-o", str(out)],
                       check=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONIOENCODING="utf-8"),
                       capture_output=True)
        digests.add(hashlib.md5(out.read_bytes()).hexdigest())
    assert len(digests) == 1
