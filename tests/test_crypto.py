import pytest
from nivo2parmis.crypto import encrypt_bytes, decrypt_bytes, NivoDecryptError


def test_roundtrip():
    raw = b"SQLite format 3\x00" + bytes(range(200))
    assert decrypt_bytes(encrypt_bytes(raw)) == raw


def test_rejects_bad_length():
    with pytest.raises(NivoDecryptError):
        decrypt_bytes(b"abc")


def test_rejects_non_sqlite():
    with pytest.raises(NivoDecryptError):
        decrypt_bytes(encrypt_bytes(b"hello world, not a database"))


def test_swapped_arguments_give_clear_error(tmp_path):
    import os
    from nivo2parmis.cli import main
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    par = os.path.join(ROOT, "examples", "parmis_template.par")
    assert main(["inspect", "--nivo", par]) == 1
