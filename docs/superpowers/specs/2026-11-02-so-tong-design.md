# Sổ tổng dạng bảng tính và thu hẹp phạm vi app — Thiết kế

Ngày: 02/11/2026 · Trạng thái: chờ người dùng duyệt

## 1. Vấn đề và mục tiêu

Người dùng thấy app bất tiện hơn Excel: Excel mở ra là thấy mọi cột, kéo ngang là xem được; app tách dữ liệu thành nhiều trang và phải bấm nhiều nút. App cũng rộng hơn nhu cầu hiện tại.

**Tiêu chí thành công:** sau khi dùng app, sheet `2026` của file "List of TVC Employees" ngừng được cập nhật. App trở thành nguồn dữ liệu duy nhất về laptop và người giữ.

## 2. Quyết định đã chốt với người dùng

| # | Quyết định |
|---|---|
| 1 | App tập trung vào laptop và con người. Các phần khác tạm gỡ, sau này bổ sung lại. |
| 2 | Cách gỡ: đánh dấu phiên bản đầy đủ trên git, gỡ code, **giữ nguyên các bảng và dữ liệu trong database**. |
| 3 | License chỉ còn dạng đánh dấu "máy nào có phần mềm nào"; bỏ seat và hạn dùng khỏi giao diện. |
| 4 | Mật khẩu giữ trong app, vẫn đi qua luồng xem có xác thực lại. |
| 5 | Sổ tổng hiện tất cả máy, kể cả máy không có mã nhân viên và máy của người đã nghỉ. |

## 3. Màn hình Sổ tổng

Trang đầu tiên sau khi đăng nhập (`/admin/so-tong`). Một bảng duy nhất, không phân trang.

**Mỗi dòng** là một laptop kèm người đang giữ. Nhân viên chưa có máy cũng có một dòng, phần thông tin máy để trống (giống file Excel).

**Cột:** Tên máy (mã KDDI), Mã GA, Số serial, Trạng thái máy, Người giữ, Mã nhân viên, userId, Email, Phòng ban, Tình trạng nhân viên, Ngày bàn giao, Ghi chú. Từ giai đoạn 2 có thêm cột phần mềm và ô mật khẩu đã che.

**Tương tác:**
- Ghim cột Tên máy và Người giữ; kéo ngang tự do.
- Ô lọc dưới mỗi tiêu đề cột; một ô tìm kiếm toàn bảng.
- Bộ lọc nhanh: Tất cả / Đang dùng / Trong kho / Đã nghỉ.
- Bấm vào tiêu đề để sắp xếp; bật tắt cột; nhớ cách sắp xếp theo từng người dùng (lưu ở trình duyệt).
- Chọn vùng ô và copy sang Excel.
- Tô màu hàng tự động: xám là người đã nghỉ, vàng là máy dùng chung MES.
- Nút Xuất Excel theo đúng bộ lọc đang chọn. File xuất ra không có mật khẩu và không bao giờ nhập ngược lại.

## 4. Kiến trúc

- **Thư viện bảng:** Tabulator (giấy phép MIT), đặt trong `static/vendor/` để không phụ thuộc CDN. Không thêm gói Python.
- **Trang:** template `templates/sqladmin/so_tong.html` kế thừa `layout.html`, router mới `app/routers/so_tong.py`.
- **Dữ liệu:** `GET /admin/api/so-tong` trả toàn bộ dòng một lần, trình duyệt tự lọc. Không dùng cache; khoảng 100 dòng nên truy vấn nhanh.
- **Tầng nghiệp vụ:** `app/services/ledger_service.py` dựng dòng dữ liệu và (từ giai đoạn 2) xử lý sửa ô. Luật không viết lại trong JavaScript.
- **Quyền:** cần `(assets, view)` và `(persons, view)`. Sửa ô theo quyền `change` của phân hệ tương ứng. Thiếu quyền trả 403 chung.
- SQLAdmin giữ lại cho các màn hình quản trị: tài khoản, thùng rác, nhật ký.

## 5. Sửa dữ liệu (giai đoạn 2)

- `PATCH /admin/api/so-tong/cell` nhận bản ghi, cột, giá trị mới; kiểm tra rồi ghi audit trước / sau.
- **Sửa trực tiếp được:** serial, mã GA, ghi chú, email, userId, phòng ban.
- **Không sửa trực tiếp:** người giữ và trạng thái máy (phải qua Bàn giao / Thu hồi để giữ lịch sử); mật khẩu.
- Bấm vào dòng mở bảng bên phải: lịch sử máy, nút Bàn giao, Thu hồi, Xem mật khẩu.
- Hai người sửa cùng ô: người lưu sau ghi đè; nhật ký vẫn lưu đủ. Chấp nhận được với 5 người dùng.

**Cột phần mềm:** dùng lại bảng `asset_tags` và `asset_tag_links` sẵn có (mỗi phần mềm là một nhãn), không cần migration. Nhập các ô "Yes" từ file Excel một lần, không đọc cột mật khẩu.

## 6. Gỡ phạm vi (giai đoạn 3)

Tạo git tag `v1-full` trước khi gỡ.

- **Gỡ:** hợp đồng, nhận hàng phần cứng và phần mềm, kho license và phân bổ bản quyền, thẻ ra vào, danh bạ điện thoại, dashboard cảnh báo, quyền riêng từng người, ma trận quyền, router `export` và `portal`, các service chỉ có test gọi.
- **Giữ:** laptop, nhân sự, bàn giao, kho mật khẩu, tài khoản, xóa mềm và thùng rác, nhật ký.
- **Vai trò:** chỉ còn hai mức hiển thị: Admin và chỉ xem. Ba mã vai trò trong database giữ nguyên.
- **Test:** test của phần bị gỡ được gỡ cùng; test của phần giữ lại phải xanh nguyên vẹn.
- **Database:** không migration xóa bảng. Dữ liệu hợp đồng, license, thẻ hiện có vẫn còn.

## 7. Thứ tự và tiêu chí chuyển bước

| Giai đoạn | Nội dung | Điều kiện sang bước sau |
|---|---|---|
| 1 | Sổ tổng chỉ xem | Người dùng xác nhận tiện hơn hoặc bằng Excel khi xem |
| 2 | Sửa ô, bảng bên phải, cột phần mềm | Người dùng dùng thật và ngừng sửa file Excel |
| 3 | Gỡ phạm vi | — |

Sổ tổng làm trước khi gỡ để nếu hướng này không đạt thì chưa mất gì.

## 8. Ngoài phạm vi

- Nhập mật khẩu từ Excel vào kho mật khẩu: là việc riêng, cần quyết định sau, vì liên quan khóa mã hóa và luồng bảo mật.
- Sửa nhiều ô cùng lúc bằng cách dán.
- Hoạt động khi không có mạng.

## 9. Kiểm thử

Viết test trước cho: nội dung API (đủ máy, đủ nhân viên chưa có máy, không có cột mật khẩu hay `*_enc`), quyền 401 / 403, bỏ bản ghi đã xóa mềm. Giai đoạn 2 thêm test cho từng ô sửa được, ô bị từ chối và audit. Kiểm tra giao diện trên trình duyệt thật ở cuối mỗi giai đoạn.
