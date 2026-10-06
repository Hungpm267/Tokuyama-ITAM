"""Cấu hình đọc từ biến môi trường. Không hardcode gì ở đây."""

import os


class Settings:
    #: Chuỗi kết nối. KHÔNG BAO GIỜ để chuỗi production trong file commit vào Git,
    #: và không đưa nó vào môi trường mà agent code có quyền chạy.
    database_url: str = os.environ.get(
        "ITAM_DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/itam_dev"
    )
    #: 'dev' hoặc 'prod'. Test chỉ chạy khi env != 'prod'.
    env: str = os.environ.get("ITAM_ENV", "dev")
    session_idle_minutes: int = 30


settings = Settings()
