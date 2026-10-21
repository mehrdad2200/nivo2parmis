"""رمزگشایی/رمزگذاری فایل پشتیبان نیوو (.nivo).

فایل .nivo یک دیتابیس SQLite است که با AES-128-ECB و padding از نوع PKCS7
رمز شده است. کلید، یک رشته‌ی ثابت داخل خود برنامه‌ی نیوو است و مخصوص هر
کاربر نیست؛ یعنی این ابزار فقط برای باز کردن فایل‌های پشتیبان خودتان است.
"""
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

NIVO_KEY = b"0192837465019283"
SQLITE_MAGIC = b"SQLite format 3"


class NivoDecryptError(ValueError):
    pass


def decrypt_bytes(data: bytes) -> bytes:
    if not data or len(data) % 16:
        raise NivoDecryptError("اندازه‌ی فایل مضرب ۱۶ نیست؛ این فایل پشتیبان نیوو نیست یا ناقص است.")
    d = Cipher(algorithms.AES(NIVO_KEY), modes.ECB()).decryptor()
    p = d.update(data) + d.finalize()
    pad = p[-1]
    if not (1 <= pad <= 16 and p[-pad:] == bytes([pad]) * pad):
        raise NivoDecryptError("padding نامعتبر؛ احتمالاً نسخه‌ی دیگری از نیوو با کلید دیگر.")
    p = p[:-pad]
    if not p.startswith(SQLITE_MAGIC):
        raise NivoDecryptError("خروجی رمزگشایی یک دیتابیس SQLite نیست.")
    return p


def encrypt_bytes(data: bytes) -> bytes:
    """فقط برای ساخت داده‌ی نمونه/تست."""
    pad = 16 - len(data) % 16
    e = Cipher(algorithms.AES(NIVO_KEY), modes.ECB()).encryptor()
    return e.update(data + bytes([pad]) * pad) + e.finalize()


def decrypt_file(src: str, dst: str) -> None:
    with open(src, "rb") as f:
        out = decrypt_bytes(f.read())
    with open(dst, "wb") as f:
        f.write(out)
