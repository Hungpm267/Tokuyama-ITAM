"""Sinh khoá mã hoá mới.

    python -m scripts.genkey

In ra một dòng base64 32 byte. Cất vào Windows Credential Manager, KHÔNG dán
vào file nằm trong repo và KHÔNG gửi qua chat/email. In một bản ra giấy cất két.
"""

from app.core.crypto import generate_key_b64

if __name__ == "__main__":
    print(generate_key_b64())
