import os, sys, importlib.util, pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def sample(tmp_path_factory):
    d = tmp_path_factory.mktemp("sample")
    spec = importlib.util.spec_from_file_location("make_example_data", os.path.join(ROOT, "examples", "make_example_data.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    nivo, parmis = m.build(str(d))
    return nivo, parmis
