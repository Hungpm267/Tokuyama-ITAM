# ITAM — Tokuyama Vietnam

Hệ thống quản lý tài sản IT nội bộ. Thay thế các file Excel quản lý thiết bị,
license, thẻ ra vào, danh bạ máy nhánh và tình trạng giao hàng theo hợp đồng.

Tài liệu nghiệp vụ: [`docs/BRD.md`](docs/BRD.md)
Quy tắc cho người và cho agent code: [`GEMINI.md`](GEMINI.md)

## Trạng thái

| Hạng mục | Tình trạng |
| --- | --- |
| Mô hình dữ liệu (23 bảng) | ✅ xong, đã chạy migration thật |
| Ràng buộc toàn vẹn ở tầng DB | ✅ xong, 28 test xanh |
| Mã hoá mật khẩu + cổng xem | ✅ xong, 22 test xanh |
| Đăng nhập, RBAC, audit log | ⬜ chưa làm |
| Các màn hình nghiệp vụ | ⬜ chưa làm |

## Cài đặt lần đầu

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 1. Sinh khoá mã hoá

```bash
python -m scripts.genkey
```

Cất giá trị in ra vào Windows Credential Manager và **in một bản ra giấy cất
két của ban giám đốc**. Mất khoá = mất toàn bộ mật khẩu đã lưu, không khôi phục
được. Không commit, không gửi qua chat hay email.

### 2. Biến môi trường

```bash
export ITAM_DATABASE_URL="postgresql+psycopg://user:pass@host:5432/itam_dev"
export ITAM_SECRET_KEY_V1="<giá trị vừa sinh>"
export ITAM_ENV=dev
```

### 3. Tạo schema và seed

```bash
alembic upgrade head
python -m scripts.seed          # tạo vai trò, quyền mặc định, tài khoản it.admin
```

## Chạy test

```bash
export ITAM_TEST_DATABASE_URL="postgresql+psycopg://postgres@127.0.0.1:5432/itam_test"
pytest
```

Fixture tự tạo lại database test. Nó từ chối chạy nếu `ITAM_ENV=prod` hoặc nếu
tên database không chứa chữ `test`.

## Sao lưu

```bash
pg_dump "$ITAM_DATABASE_URL" -Fc -f backup_$(date +%F).dump
```

Chạy hằng ngày về máy công ty. **Kiểm thử khôi phục ít nhất một lần trước
go-live** — một bản backup chưa từng được khôi phục thử thì chưa phải backup.

Bản dump KHÔNG chứa khoá mã hoá. Khôi phục mà không có khoá thì các cột
`*_enc` là dữ liệu vô nghĩa. Giữ hai thứ ở hai nơi khác nhau là có chủ ý.

## Xoay khoá mã hoá

Khi nghi ngờ khoá bị lộ (mất laptop chẳng hạn):

1. `python -m scripts.genkey` → đặt thành `ITAM_SECRET_KEY_V2`, giữ nguyên `V1`.
2. Chạy script rewrap để mã lại từng bản ghi bằng `SecretBox.rewrap()`.
3. Khi `key_version = 2` trên mọi bản ghi, gỡ `ITAM_SECRET_KEY_V1`.
4. **Đổi luôn toàn bộ mật khẩu nhân viên** — xoay khoá không làm mất hiệu lực
   những bản mã kẻ khác đã sao chép được.

## Phục hồi khi IT không có mặt

Cần đúng ba thứ: repo Git, bản `pg_dump` mới nhất, và khoá mã hoá trong két.
Có cả ba thì dựng lại hệ thống trên một máy khác theo mục "Cài đặt lần đầu".
