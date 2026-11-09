# Dọn master data, loại nhân sự, mã thiết bị, làm gọn Kho mật khẩu

Ngày: 09/11/2026. Trạng thái: chờ người dùng duyệt.

## Bối cảnh và lý do

Người dùng (IT Admin, người duy nhất nhập liệu) thấy các màn hình danh mục rối vì hiện những cột không mang
nghĩa nghiệp vụ (ID, mã phòng ban, mã tem GA), và màn hình Kho mật khẩu quá nhiều chữ. Tokuyama Vietnam là nhà
máy mới, ít phòng ban; thực tế IT đặt mã riêng cho mọi thiết bị (TKY-PC0001 cho laptop, mã tương tự cho thiết
bị khác) và không dùng tem GA.

Dữ liệu thật (bản sao lưu 08/11/2026): 71 tài sản, tất cả là Laptop, cả 71 có PC name, **không tài sản nào có
mã GA**. 66 nhân sự, một số không có mã nhân viên vì là vendor thuê tạm hoặc người Nhật sang công tác. 8 phòng
ban, mã phòng ban không được nơi nào dùng.

## Mục tiêu

1. Màn hình không còn hiện cột ID ở bất kỳ danh sách / chi tiết / form nào của app.
2. Phòng ban chỉ còn tên. Bỏ hẳn cột mã phòng ban.
3. Bỏ hẳn mã tem GA (`assets.asset_code`) khỏi toàn app và database.
4. PC name thành **Mã thiết bị**, dùng chung cho mọi loại tài sản, **bắt buộc** và **duy nhất**.
5. Nhân sự có **loại**: Nhân viên chính thức / Vendor / Công tác Nhật. Vendor và người công tác được app tự cấp mã.
6. Ẩn menu "Nhãn tài sản"; danh mục phần mềm quản lý ngay trên Sổ tổng.
7. Kho mật khẩu làm lại theo hướng A ("một bảng gọn") người dùng đã chọn.

## Không làm

- Không bỏ cột `id` trong database (người dùng đồng ý sau khi nghe lý do: mã có thể đổi, vendor có thể thành
  nhân viên chính thức; khóa chính phải không đổi để lịch sử bàn giao không đứt).
- Không đổi tên phòng ban hiện có (người dùng quyết định giữ nguyên).
- Không xóa bảng `asset_tags` (đang chứa phần mềm `SW-` và màu đánh dấu `MARK-` của Sổ tổng).
- Không đổi cách mã hóa / cổng xem mật khẩu (RevealGate, audit REVEAL) — chỉ đổi giao diện.

## Thất bại dù chạy được

- Lịch sử bàn giao hoặc mật khẩu bị gắn nhầm người sau khi đổi mã / đổi loại nhân sự.
- Mật khẩu hoặc cột `*_enc` lọt ra trang mới (response, HTML, log).
- Tài sản đang có bị từ chối lưu vì quy tắc mã thiết bị mới.
- Người chỉ xem lại thấy được nút sửa / xem mật khẩu.

## 1. Ẩn ID trên mọi màn hình

- Bỏ `id` khỏi `column_list`, `column_details_list`, `column_searchable_list`, `column_sortable_list` của mọi
  view trong `app/admin.py`; thay bằng cột nghiệp vụ (mã thiết bị, mã nhân viên, tên).
- Các trang tùy biến (`details.html`, `global_search.html`, `trash`, Sổ tổng, Kho mật khẩu, nhật ký audit) không
  hiện số ID cho người đọc. Đường dẫn URL nội bộ (`/admin/asset/details/5`) vẫn dùng id — không phải cột hiển thị.
- Nhật ký truy vết (audit) hiện tên / mã của bản ghi thay cho "Asset #5" khi tra được; nếu bản ghi đã bị xóa hẳn
  thì giữ "#id". (Lựa chọn của agent.)

## 2. Phòng ban chỉ còn tên

- Migration bỏ cột `departments.code` và partial unique index của nó. Tên vẫn duy nhất (index hiện có).
- Bỏ mọi chỗ code / template / i18n / test đang dùng `Department.code`; `__str__` trả tên.
- Màn hình Phòng ban chỉ còn: Tên (EN/VI), Tên tiếng Nhật.

## 3. Bỏ mã tem GA, PC name thành Mã thiết bị

- Migration: bỏ cột `assets.asset_code` và index của nó; đổi `assets.pc_name` → `assets.device_code`
  (tên cột là lựa chọn của agent, builder được đổi nếu có lý do); đặt `NOT NULL`; giữ partial unique trên bản
  ghi còn sống (đổi tên index theo cột).
- CHECK `has_some_identifier` không còn cần (mã thiết bị đã bắt buộc) → bỏ.
- Migration phải **dừng với thông báo rõ** nếu có tài sản (kể cả đã xóa mềm) có `asset_code` khác NULL, hoặc
  `pc_name` NULL, thay vì làm mất dữ liệu. (Dữ liệu 08/11 không có trường hợp nào.)
- Nhãn hiển thị: **"Mã thiết bị"** / "Device code" / 「機器コード」. Sổ tổng: cột "Tên máy" thành "Mã thiết bị".
- Bỏ mã GA ở: Sổ tổng (cột, ô sửa, panel), form + danh sách SQLAdmin, tìm kiếm chung, thùng rác (kiểm trùng khi
  khôi phục), trang chi tiết, modal bàn giao, xuất CSV, `ledger_service.ASSET_TEXT_FIELDS`, `assignment_service`,
  thông báo lỗi `humanize_error_str`, i18n, `docs/database.dbml`, test.
- Sửa mã thiết bị trên Sổ tổng: cho phép (ô sửa trực tiếp), kiểm trùng không phân biệt hoa thường, không cho để
  trống. (Hiện Sổ tổng chưa cho sửa PC name — đây là thêm mới, lựa chọn của agent vì mã giờ là định danh chính.)

## 4. Loại nhân sự và mã tự cấp

### Người dùng quyết định
- Ba loại: **Nhân viên chính thức**, **Vendor**, **Công tác Nhật**.
- Vendor và người công tác được app tự cấp mã dạng `VND-001`, `JP-001`. Nhân viên chính thức giữ mã TVC.

### Hành vi
- Cột mới `persons.person_type` (ENUM `EMPLOYEE` / `VENDOR` / `BUSINESS_TRIP`), mặc định `EMPLOYEE`.
- Tạo nhân sự loại Vendor / Công tác Nhật mà ô mã để trống → app cấp mã tiếp theo: lớn nhất hiện có (kể cả đã
  xóa mềm, để không cấp lại mã cũ) + 1, đủ 3 chữ số (`VND-001`, …, `VND-999`, `VND-1000`).
- Nhân viên chính thức: mã nhân viên **bắt buộc** từ nay (nhập tay, như hiện tại). Vendor / công tác: được nhập tay
  nếu muốn, để trống thì tự cấp.
- Sau khi áp dụng, **mọi nhân sự đều có mã** → `staff_code` thành `NOT NULL` trong DB (vẫn duy nhất trên bản ghi
  sống). Không dùng làm khóa chính (giữ `id`).
- Mã phải khớp loại (lựa chọn của agent): nhân viên chính thức **không** được dùng mã bắt đầu `VND-` / `JP-`;
  Vendor phải là `VND-…`, Công tác Nhật phải là `JP-…` (nhập tay đúng tiền tố hoặc để trống cho app cấp). Đổi loại
  mà mã không khớp loại mới → báo lỗi, trừ khi để trống mã ở loại Vendor / Công tác (app cấp mã mới). Số tiếp theo
  chỉ tính trên các mã đúng mẫu `VND-<số>` / `JP-<số>`. Áp ở cả form SQLAdmin và mọi chỗ sửa nhân sự khác.
- Đổi loại nhân sự (vd vendor thành nhân viên chính thức): người dùng sửa loại và nhập mã TVC mới; lịch sử bàn
  giao và mật khẩu đi theo người (khóa `id` không đổi). Audit ghi mã cũ → mã mới.
- Cột "Loại nhân sự" hiện ở danh sách nhân sự, Sổ tổng (lọc được) và Kho mật khẩu (dòng phụ dưới tên).

### Dữ liệu hiện có
- Người đang có mã → `EMPLOYEE`.
- 6 người chưa có mã (bản sao lưu 08/11, đều còn sống), người dùng phân loại:
  - **Vendor**: Hoang Duc Long, Hoàng Thị Mai, Le Nguyen Nhat Khanh → `VND-001`, `VND-002`, `VND-003` theo thứ tự tên.
  - **Công tác Nhật**: Katou, Sugimoto Hirokazu, Takeda Aki → `JP-001`, `JP-002`, `JP-003` theo thứ tự tên.
  - Người dùng chưa chắc Le Nguyen Nhat Khanh có phải nhân viên chính thức không: tạm để Vendor; nếu đúng là
    nhân viên thì sửa loại và nhập mã TVC trên app sau, lịch sử đi theo người.
- Migration `0007` áp phân loại này, nhận diện theo **email** (ổn định hơn tên). Ai còn thiếu mã mà không có trong
  danh sách (người mới tạo sau 08/11, hoặc bản ghi đã xóa mềm) → mặc định `VENDOR` và nhận mã `VND-` tiếp theo; migration
  in ra danh sách này. (Lựa chọn của agent.)

## 5. Ẩn menu Nhãn tài sản, quản lý phần mềm trên Sổ tổng

- Bỏ "Nhãn tài sản" khỏi thanh bên (view không còn hiển thị trong menu; không xóa bảng).
- Hộp "Quản lý màu" trên Sổ tổng mở rộng thành hộp có hai phần: **Màu đánh dấu** (như hiện tại) và **Phần mềm**
  (thêm / đổi tên / xóa mục phần mềm `SW-…`; xóa mục đang gắn trên máy thì hỏi lại như phần màu). (Lựa chọn của
  agent, người dùng chưa xác nhận chỗ đặt.)

## 6. Kho mật khẩu — hướng A "một bảng gọn" (người dùng đã chọn)

- Tiêu đề một dòng "Kho mật khẩu" kèm biểu tượng khóa; bên phải là "N / M người đã lưu". Bỏ đoạn giải thích
  AES / 2 lớp / Audit ở đầu trang; thay bằng một dòng nhỏ cuối bảng: "Mỗi lần xem mật khẩu đều được ghi lại."
- Một ô tìm kiếm (tên, mã, phòng ban, email). Bộ lọc dạng chip: **Tất cả / Thiếu PC / Thiếu Email**.
- Bảng 3 cột: **Nhân sự** (tên đậm; dòng phụ: mã · phòng ban hoặc loại nhân sự), **PC**, **Email**. Mỗi ô mật
  khẩu: nhãn "✓ Đã lưu" (xanh) hoặc "— Chưa có" (xám); nếu đã lưu có nút mắt để xem (đi qua RevealGate như cũ).
- Bấm vào một dòng → hộp sửa (nhập / đổi / xóa mật khẩu PC và Email, ghi chú) — chức năng như các nút Sửa / Xóa
  hiện tại.
- Nút "Khóa phiên" và "Tải lại" gom thành một nút nhỏ ở góc; bỏ nút trùng chức năng.
- Ba ngôn ngữ, giao diện điện thoại (bảng thành danh sách thẻ, giống Sổ tổng).
- Dùng skill `frontend-design` khi dựng (người dùng yêu cầu). Giữ màu chủ đạo `#4D5CB0` của app.

## Ràng buộc

- Các bất biến trong `CLAUDE.md` giữ nguyên: xóa mềm, audit, `REDACTED_FIELDS`, `today_local()`, `inputs.py`.
- Schema đổi qua Alembic `0007`, cập nhật `models.py`, `docs/database.dbml`, `tests/test_schema_cleanup.py`.
- Test viết trước. Toàn bộ test và `ruff` sạch. Kiểm tra trên trình duyệt (bản sao local, không phải Aiven).
- Lên production: sao lưu → migration → merge `main` vào `master` (Render deploy từ `master`) → kiểm tra. Mỗi bước
  trên Aiven cần người dùng cho phép. Render không tự chạy migration; giữa lúc migration chạy và lúc deploy xong (khoảng
  một phút) app cũ sẽ báo lỗi ở các trang tài sản. Chấp nhận một migration duy nhất, làm vào giờ ít người dùng
  như lần `0005`. (Lựa chọn của agent.)

## Để builder quyết định

- Cách ẩn view trong menu SQLAdmin, tên cột / ENUM cụ thể, bố cục chi tiết hộp quản lý trên Sổ tổng.
- Cách hiển thị tên bản ghi trong nhật ký audit.

