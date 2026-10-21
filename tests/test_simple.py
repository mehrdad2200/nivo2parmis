import os, time
from nivo2parmis.simple import find_files, default_output, run_job


def test_find_files_ignores_merged_and_takes_newest(tmp_path):
    for n, age in (("old.par", 300), ("new.par", 100), ("parmis-merged.par", 0), ("a.nivo", 50)):
        p = tmp_path / n; p.write_bytes(b"x"); t = time.time() - age; os.utime(p, (t, t))
    nivo, parmis = find_files(str(tmp_path))
    assert os.path.basename(nivo) == "a.nivo" and os.path.basename(parmis) == "new.par"


def test_default_output_never_overwrites(tmp_path):
    par = tmp_path / "p.par"; par.write_bytes(b"x")
    first = default_output(str(par)); open(first, "wb").close()
    assert os.path.basename(first) == "parmis-merged.par"
    assert os.path.basename(default_output(str(par))) == "parmis-merged-2.par"


def test_run_job_end_to_end(sample, tmp_path):
    import shutil
    par = tmp_path / "p.par"; shutil.copy(sample[1], par)
    out, rep = run_job(sample[0], str(par), log=lambda *a: None)
    assert os.path.exists(out) and rep["inserted"] == 87 and all(ok for _, ok, _ in rep["checks"])
