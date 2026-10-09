# Hướng dẫn Sử dụng Hệ thống Quản lý Tài sản IT (ITAM)
## Tokuyama Vietnam Co., Ltd.

---

## 1. Giới thiệu Tổng quan & Đăng nhập Hệ thống

Hệ thống **Tokuyama Vietnam ITAM (IT Asset Management)** là ứng dụng web quản trị nội bộ dành cho Công ty TNHH Tokuyama Việt Nam, thay thế toàn bộ quy trình quản lý tài sản thủ công trên Excel trước đây. Hệ thống quản lý toàn diện vòng đời tài sản CNTT: từ phần cứng máy tính, bản quyền phần mềm, thẻ từ ra vào, thiết bị thoại, hợp đồng mua sắm, đến kho bảo mật mật khẩu nhân sự và nhật ký kiểm toán bất biến.

### 1.1. Địa chỉ truy cập & Phiên bản
- **URL truy cập:** `http://<ip-hoac-ten-mien>:8000/admin` (hoặc cổng cấu hình của công ty).
- **Trình duyệt khuyến nghị:** Google Chrome, Microsoft Edge, Mozilla Firefox phiên bản mới nhất.

### 1.2. Các nhóm người dùng & Phân quyền truy cập (RBAC)
Hệ thống được thiết kế phục vụ 3 nhóm đối tượng chính với thẩm quyền chặt chẽ:

| Vai trò (Role) | Chức danh / Nhóm người dùng | Phạm vi thẩm quyền trên hệ thống |
| :--- | :--- | :--- |
| **ADMINISTRATOR** (`ADMIN`) | Quản trị viên IT (1 người) | Toàn quyền quản trị tất cả các phân hệ: thêm/sửa/xóa tài sản, cấu hình người dùng, phân quyền RBAC, xem kho mật khẩu nhân viên (Secret Vault), khôi phục dữ liệu từ Thùng rác. |
| **GA MANAGER** (`GA_MANAGER`) | Trưởng phòng Tổng vụ (1 người) | Quản lý danh mục tài sản, thực hiện bàn giao/thu hồi máy tính, cho mượn/trả thẻ từ ra vào, theo dõi tiến độ hợp đồng mua sắm IT, danh bạ thoại. **Không có quyền** truy cập kho mật khẩu và quản trị tài khoản hệ thống. |
| **EXECUTIVE** (`EXECUTIVE`) | Ban Giám đốc người Nhật (3 người) | Quyền xem dữ liệu báo cáo (Read-only) trên các bảng danh sách: Tài sản phần cứng, License phần mềm, Hợp đồng, Thẻ từ, Nhật ký kiểm toán. |

### 1.3. Hướng dẫn Đăng nhập
1. Truy cập vào đường dẫn `/admin`. Nếu chưa đăng nhập, hệ thống sẽ tự động chuyển hướng đến màn hình **Đăng nhập Hệ thống ITAM**.
2. Nhập **Tên đăng nhập** (`Username`) và **Mật khẩu** (`Password`).
3. Nhấn **Đăng nhập** (`Sign In` / `ログイン`).
   - Mật khẩu đăng nhập được băm bảo mật bằng thuật toán **Argon2id**.
   - Sau khi đăng nhập thành công, hệ thống mở trực tiếp Giao diện Điều khiển Quản trị (`/admin`).

### 1.4. Chuyển đổi Ngôn ngữ Giao diện (VI / EN / JA)
Tại thanh điều hướng trên cùng bên phải (`Top Utility Bar`), hệ thống tích hợp bộ chuyển đổi 3 ngôn ngữ theo thời gian thực:
- **Tiếng Việt (`VI`)**: Ngôn ngữ mặc định cho nhân sự vận hành tại nhà máy/văn phòng.
- **English (`EN`)**: Ngôn ngữ quốc tế cho công tác đối ngoại và quy chuẩn IT.
- **日本語 (`JA`)**: Ngôn ngữ bản địa dành riêng cho Ban Giám đốc và chuyên gia Nhật Bản.

*Cách đổi:* Nhấp chuột trực tiếp vào nhãn `Tiếng Việt`, `English` hoặc `日本語`. Toàn bộ danh mục menu, tiêu đề bảng, tên thuộc tính, huy hiệu trạng thái và các thông báo xác nhận sẽ lập tức đổi sang ngôn ngữ đã chọn.

---

## 2. Giao diện Điều khiển & Tìm kiếm Toàn cục

### 2.1. Thanh menu bên trái (Sidebar Navigation)
Menu bên trái được phân nhóm logic theo từng phân hệ nghiệp vụ:
1. **Hệ thống & Phân quyền (`システム・権限管理`):** Người dùng, Vai trò, Ma trận Quyền, Ghi đè Quyền.
2. **Danh mục Dùng chung (`マスタ管理`):** Phòng ban, Loại tài sản, Nhãn (Tags), Vị trí/Phòng.
3. **Nhân sự (`社員・人事`):** Hồ sơ Nhân sự, Kho Mật khẩu Nhân sự.
4. **Tài sản (`IT資産・機器`):** Danh sách Thiết bị, Lịch sử Cấp phát Tài sản.
5. **License (`ソフトウェアライセンス`):** Danh mục Sản phẩm, Danh sách License, Cấp phát License.
6. **Thẻ ra vào (`入退室カード`):** Danh sách Thẻ từ, Sổ Mượn-Trả Thẻ.
7. **Hợp đồng (`調達契約`):** Danh sách Hợp đồng mua sắm, Chi tiết Hạng mục đơn hàng.
8. **Danh bạ thoại (`内線電話帳`):** Danh bạ & Thiết bị Điện thoại.
9. **Truy vết (`監査ログ`):** Nhật ký Hoạt động (Audit Trail).

### 2.2. Tìm kiếm nhanh toàn cục (Global Search) & Phím tắt `Ctrl + K`
- **Cách dùng:** Nhấn tổ hợp phím **`Ctrl + K`** (hoặc `Cmd + K` trên macOS) ở bất kỳ trang nào để đưa con trỏ vào ô tìm kiếm trên thanh điều hướng đầu trang.
- **Phạm vi tìm kiếm:**
  - **Mã tài sản GA** (ví dụ: `GA-LAP-001`)
  - **Số Serial máy** (ví dụ: `PF3Z9X11`)
  - **Địa chỉ MAC** (LAN/Wifi)
  - **Mã nhân viên & Họ tên** (ví dụ: `TVC00012`, `Nguyễn Văn A`)
  - **Mã số thẻ từ** (ví dụ: `CARD-015`)
  - **Số hợp đồng mua sắm** (ví dụ: `KHCM-2026-001`)
- Kết quả được gom nhóm theo từng phân hệ trực quan, có huy hiệu màu phân biệt và liên kết nhấp chuột trực tiếp đến trang chi tiết bản ghi.

---

## 3. Quản lý Tài sản Phần cứng (Hardware Assets)

### 3.1. Danh sách Thiết bị IT (`/admin/asset/list`)
Quản lý toàn bộ vòng đời của laptop, máy để bàn, màn hình, máy in...
- **Trạng thái thiết bị (`Status`):**
  - `IN_STOCK` (Trong kho / 在庫): Sẵn sàng bàn giao sử dụng.
  - `IN_USE` (Đang sử dụng / 使用中): Đã cấp phát cho nhân viên quản lý.
  - `MAINTENANCE` (Đang sửa chữa / 修理中): Đang bảo hành, sửa chữa.
  - `DISPOSED` (Đã thanh lý / 廃棄済み): Đã thu hồi tiêu hủy hoặc bán thanh lý.
- **Ràng buộc duy nhất:** Số Serial và Mã tài sản GA không được phép trùng lặp giữa các máy đang hoạt động.

### 3.2. Quy trình Bàn giao Thiết bị (Assignment)
> **Bất biến hệ thống:** Mỗi thiết bị chỉ được có tối đa **MỘT** lượt bàn giao đang mở (`returned_at IS NULL`). Không thể bàn giao một chiếc máy đang có người sử dụng.

1. Tại danh sách thiết bị hoặc trang chi tiết thiết bị, nhấn nút **Bàn giao** (`Assign` / `割当`).
2. Chọn **Nhân viên nhận máy** từ danh sách nhân sự (tìm theo Mã NV hoặc Tên).
3. Chọn **Ngày bàn giao** (`borrowed_at`) - mặc định là ngày hiện tại.
4. Nhập ghi chú phụ kiện bàn giao (ví dụ: Sạc type-C 65W, Chuột không dây, Cặp laptop...).
5. Nhấn **Xác nhận bàn giao**. Hệ thống sẽ:
   - Tự động chuyển trạng thái thiết bị sang `IN_USE`.
   - Cập nhật tên người đang giữ máy trên danh sách.
   - Ghi lại vết bàn giao vào lịch sử cấp phát và bảng kiểm toán `AuditLog`.

### 3.3. Quy trình Thu hồi Thiết bị (Return)
1. Khi nhân viên chuyển vị trí, nghỉ việc hoặc đổi máy, bấm nút **Thu hồi** (`Return` / `返却`) tại dòng tài sản đó.
2. Chọn **Ngày thu hồi** (`returned_at`). Hệ thống kiểm tra ràng buộc `Ngày thu hồi >= Ngày bàn giao`.
3. Nhập hiện trạng thu hồi (ví dụ: Máy hoạt động bình thường, màn hình trầy nhẹ...).
4. Chọn trạng thái sau thu hồi: **Nhập lại kho** (`IN_STOCK`) hoặc **Chuyển sửa chữa** (`MAINTENANCE`).
5. Xác nhận: Lịch sử bàn giao cũ được đóng lại (không bị xóa), máy trở về trạng thái sẵn sàng.

### 3.4. Nhập kho theo lô (Batch Receive Asset)
Khi ký hợp đồng mua sắm mới về 20-50 máy tính, không cần tạo thủ công từng chiếc:
1. Nhấn nút **Nhập kho theo lô** (`Batch Receive` / `一括受入・入庫`) trên thanh công cụ trang Danh sách thiết bị.
2. Chọn **Hợp đồng & Hạng mục hợp đồng** liên kết (Contract Line).
3. Chọn thông số cấu hình chung (Loại tài sản, Hãng sản xuất, Model, CPU, RAM, Ổ cứng...).
4. Nhập bảng danh sách hàng loạt:
   - Cột Mã GA, Số Serial, Địa chỉ MAC LAN, MAC Wifi (có thể dán trực tiếp từ bảng Excel nhà cung cấp gửi).
5. Nhấn **Tiến hành nhập kho**: Hệ thống tự động kiểm tra trùng lặp serial và tạo toàn bộ bản ghi trong một giao dịch duy nhất, đồng thời tự động cập nhật số lượng đã nhận (`qty_delivered`) của Hợp đồng.

---

## 4. Quản lý Nhân sự & Kho Mật khẩu Bảo mật (Secret Vault)

### 4.1. Quản lý Hồ sơ Nhân sự (`/admin/person/list`)
- Quản lý mã nhân viên (`staff_code` chuẩn định dạng `TVCxxxxx`), họ và tên, phòng ban, chức danh, tình trạng công tác (`ACTIVE`, `PROBATION`, `RESIGNED`), số điện thoại, ngày vào làm.
- Trang chi tiết nhân sự tổng hợp: Các thiết bị máy tính đang giữ, các bản quyền phần mềm đang được cấp, và thẻ từ ra vào đang mượn.

### 4.2. Kho Mật khẩu Nhân sự (`/admin/person-secret/list`) & Cơ chế Mở khóa An toàn (FR-06)
> ⚠️ **Quy tắc An ninh Bất biến:** Mật khẩu Windows/Email của nhân viên là thông tin cực kỳ nhạy cảm. Toàn bộ mật khẩu được mã hóa phần cứng bằng giải thuật **AES-256-GCM** với khóa độc lập trong môi trường máy chủ. Chỉ tài khoản Quản trị viên (`ADMIN`) mới có quyền thực hiện luồng xem mật khẩu.

#### Luồng Giải mã Mật khẩu (Reveal Gate Workflow):
1. **Mặc định bảo vệ:** Màn hình luôn che giấu mật khẩu dưới dạng chấm đen `••••••••` để chống chụp trộm màn hình (shoulder-surfing).
2. Khi cần giải mã (hỗ trợ nhân viên quên mật khẩu, kiểm tra khi nghỉ việc):
   - Nhấn nút **Xem mật khẩu** (`Reveal` / `表示`) cạnh trường mật khẩu cần xem.
   - Một hộp thoại xác thực an ninh xuất hiện: **Yêu cầu nhập lại chính mật khẩu đăng nhập hệ thống của Admin**.
3. **Kiểm tra mật khẩu Admin:**
   - Nếu nhập sai: Báo lỗi. Nếu cố tình nhập sai quá 5 lần trong 15 phút, tài khoản sẽ bị tạm khóa an ninh 15 phút.
   - Nếu nhập đúng: Hệ thống cấp một vé ủy quyền tạm thời (Token) có hiệu lực tối đa **2 phút**.
4. **Hiển thị có kiểm soát:**
   - Mật khẩu giải mã hiển thị trên màn hình kèm đồng hồ đếm ngược an ninh.
   - **Tự động ẩn lại sau 60 giây**: Trình duyệt sẽ tự động xóa sạch mật khẩu khỏi giao diện để bảo vệ thông tin.
   - **Ghi nhật ký kiểm toán tức thì:** Mỗi lượt xem mật khẩu thành công sẽ tạo ngay một bản ghi kiểm toán mang hành động `REVEAL`, lưu rõ: Ai đã xem, xem mật khẩu của nhân viên nào, vào lúc mấy giờ và từ địa chỉ IP nào.

---

## 5. Quản lý Bản quyền Phần mềm (Software Licenses)

### 5.1. Danh mục Phần mềm & Kho Bản quyền
- **Danh mục Sản phẩm (`LicenseProduct`):** Quản lý tên phần mềm (Microsoft 365, AutoCAD, SolidWorks, Windows 11 Pro...), phiên bản và nhà sản xuất.
- **Kho Bản quyền (`License`):** Quản lý chi tiết từng gói key mua: Loại bản quyền (Theo thiết bị - `PER_DEVICE`, Theo nhân viên - `PER_USER`, hoặc Dung lượng máy chủ - `SITE`), Mã bản quyền (Key được mã hóa an toàn), Tổng số lượng chỗ sử dụng (Total Seats).

### 5.2. Cấp phát & Theo dõi Giới hạn Số lượng (Seat Limits)
- Gán bản quyền cho máy tính hoặc trực tiếp cho nhân sự.
- Hệ thống tự động tính toán số ghế:
  $$\text{Số lượng còn lại (Remaining Seats)} = \text{Tổng số lượng (Total)} - \text{Đang cấp phát (Active Assignments)}$$
- Khi số ghế còn lại bằng 0, hệ thống tự động ngăn chặn việc gán thêm và đưa ra cảnh báo thân thiện: *"Gói bản quyền đã hết lượt sử dụng"*.
- Khi nhân viên thôi dùng hoặc máy tính thu hồi: Bấm **Thu hồi bản quyền** (`Revoke License`), bản ghi được đóng ngày kết thúc và số seat khả dụng tự động tăng trở lại.

---

## 6. Quản lý Thẻ Từ Ra Vào (Access Cards) & Cho Mượn Thẻ

### 6.1. Danh sách Thẻ từ (`/admin/access-card/list`)
- Quản lý mã số thẻ in trên vỏ và mã chip từ.
- Phân loại thẻ:
  - `STAFF`: Thẻ định danh cố định của nhân viên Tokuyama.
  - `CONTRACTOR`: Thẻ dùng cho nhà thầu thi công, đối tác kỹ thuật ngoài vào nhà máy làm việc ngắn ngày.
  - `GUEST`: Thẻ cho khách tham quan văn phòng.
- Trạng thái thẻ: `IN_STOCK` (Trong tủ thẻ), `BORROWED` (Đang cho mượn), `LOST` (Báo mất thẻ), `DAMAGED` (Hỏng chip/hỏng vỏ).

### 6.2. Sổ Mượn - Trả Thẻ (`CardLoan`)
- Cho phép lập phiếu mượn thẻ linh hoạt:
  - Mượn cho **Nhân viên nội bộ**: Chọn nhân viên từ danh sách.
  - Mượn cho **Nhà thầu ngoài**: Nhập họ tên đối tác và công ty đại diện (ví dụ: *Yamada Taro - Công ty Tokyo Systems*).
- Ghi nhận ngày mượn, ngày dự kiến trả và mục đích vào nhà máy.
- **Quy tắc an toàn:** Không thể cho mượn một thẻ đang có trạng thái `BORROWED`. Khi người mượn hoàn trả thẻ, bấm nút **Trả thẻ** (`Return Card`), nhập ngày trả và hiện trạng thẻ để đưa thẻ về trạng thái `IN_STOCK`.

---

## 7. Hợp đồng Mua sắm, Danh bạ Thoại & Thùng Rác Dữ Liệu

### 7.1. Theo dõi Hợp đồng Mua sắm IT (`Contract & Contract Lines`)
> **Quy tắc chống sai lệch số liệu:** Hệ thống tuyệt đối không cho phép gõ tay số lượng máy đã giao. Số lượng nhận hàng được đếm tự động 100% từ số máy thực tế có gắn `contract_line_id` trong hệ thống.

- Quản lý số hợp đồng, nhà cung cấp (KDDI, FPT, Dell...), ngày ký kết.
- Mỗi hợp đồng gồm nhiều hạng mục (ví dụ: 10 Laptop ThinkPad T14, 5 Màn hình Dell 24-inch).
- Bảng hiển thị tự động thanh tiến độ nhận hàng (`Delivery Progress`):
  - **Chưa nhận (`PENDING`):** Đã nhận = 0.
  - **Giao một phần (`PARTIAL`):** $0 < \text{Đã nhận} < \text{Đặt mua}$.
  - **Đã đủ hàng (`COMPLETED`):** Đã nhận = Đặt mua.

### 7.2. Danh bạ Nội bộ & Thiết bị Thoại (`PhoneDevice`)
- Quản lý số máy nhánh nội bộ (Ext), địa chỉ IP điện thoại bàn (IP Phone), dòng máy, vị trí lắp đặt và nhân viên phụ trách trực máy.
- Giúp nhân viên và bộ phận lễ tân/GA tra cứu nhanh đầu số liên lạc nội bộ trong nhà máy.

### 7.3. Thùng rác & Khôi phục Dữ liệu (Soft-Delete & Trash Recovery)
- **Cơ chế Xóa mềm (Soft-Delete):** Khi xóa một bản ghi (Thiết bị, Nhân viên, Hợp đồng, Thẻ...), dữ liệu không bị xóa vĩnh viễn khỏi Database mà được đánh dấu `is_deleted = true`, kèm thời điểm xóa, người xóa và **Lý do xóa bắt buộc** (để đảm bảo tính minh bạch).
- **Trang Thùng rác (`/admin/trash`):**
  - Quản trị viên (`ADMIN`) có thể xem toàn bộ các bản ghi đã xóa theo từng danh mục.
  - Bấm nút **Khôi phục (`Restore` / `復元`)** để đưa bản ghi trở lại hoạt động bình thường sau khi hệ thống tự động kiểm tra lại tính hợp lệ của Serial/Mã số.

---

## 8. Quản trị Hệ thống, Phân quyền RBAC & Nhật ký Kiểm toán

### 8.1. Quản lý Tài khoản Đăng nhập & Đổi mật khẩu
- Quản trị viên có thể tạo mới tài khoản cho nhân sự mới, chỉ định vai trò (`Role`) và ngôn ngữ ưa thích (`preferred_lang`).
- Để đổi mật khẩu cho người dùng: Vào chỉnh sửa người dùng, nhập mật khẩu mới vào ô "Mật khẩu" (tối thiểu 6 ký tự) và bấm Lưu. Nếu để trống, mật khẩu cũ được giữ nguyên.

### 8.2. Ma trận Phân quyền Vai trò trực quan (`/admin/role-permission/list`)
- Cho phép Admin xem và thiết lập trực quan ma trận quyền hạn giữa các **Vai trò** (ADMIN, GA_MANAGER, EXECUTIVE) và các **Phân hệ** (Users, Persons, Assets, Licenses, Cards, Contracts, Audit) theo 4 hành động:
  - `View` (Xem danh sách & Chi tiết)
  - `Add` (Tạo mới bản ghi)
  - `Change` (Chỉnh sửa thông tin)
  - `Delete` (Xóa mềm bản ghi)
- Có nút **Lưu ma trận** và nút **Khôi phục mặc định** (`Reset to Defaults`) để đưa quyền hạn về cấu hình chuẩn ban đầu theo quy chế công ty.

### 8.3. Nhật ký Kiểm toán Bất biến (Audit Trail - `/admin/audit-log/list`)
> **Bảo vệ chống gian lận:** Bảng `audit_logs` được cài đặt Trigger khóa cứng ở tầng cơ sở dữ liệu PostgreSQL. Ngay cả người có tài khoản kết nối Database trực tiếp cũng chỉ có quyền `INSERT` và `SELECT`, **tuyệt đối không thể UPDATE hay DELETE**.

- Tự động ghi lại nhật ký cho mọi hành động trọng yếu:
  - `CREATE`: Tạo mới dữ liệu.
  - `UPDATE`: Chỉnh sửa dữ liệu (lưu lại chi tiết giá trị trước và sau khi sửa).
  - `DELETE`: Xóa mềm dữ liệu (lưu kèm lý do xóa).
  - `RESTORE`: Khôi phục bản ghi từ thùng rác.
  - `LOGIN` & `LOGIN_FAIL`: Đăng nhập thành công hoặc thất bại kèm địa chỉ IP.
  - `REVEAL`: Giải mã xem mật khẩu nhân viên.
- Mọi dữ liệu mật khẩu gốc (`password_hash`, `pc_password_enc`...) đều được tự động gắn cờ `[REDACTED]` trước khi ghi nhật ký, triệt tiêu hoàn toàn nguy cơ lộ lọt thông tin nhạy cảm.

---

## 9. Hướng dẫn Xử lý Sự cố Thường gặp (Troubleshooting)

| Tình huống / Thông báo lỗi | Nguyên nhân | Hướng xử lý |
| :--- | :--- | :--- |
| **"Thiết bị này hiện đang được bàn giao cho nhân viên khác sử dụng (chưa thu hồi)"** | Thiết bị đang có 1 phiếu cấp phát chưa đóng ngày trả. | Vào Lịch sử cấp phát của thiết bị đó, thực hiện Thu hồi (`Return`) trước khi bàn giao cho người mới. |
| **"Số Serial này đã tồn tại trong hệ thống (bị trùng lặp)"** | Máy tính có serial này đã được tạo trước đó hoặc đang nằm trong Thùng rác. | Kiểm tra lại số serial hoặc kiểm tra mục Thùng rác để khôi phục thay vì tạo mới. |
| **"Bản quyền này đã hết lượt gán (0 seats remaining)"** | Toàn bộ số bản quyền mua đã được gán hết cho nhân viên/thiết bị. | Kiểm tra danh sách gán để thu hồi từ các máy không dùng, hoặc liên hệ GA lập hợp đồng mua thêm bản quyền. |
| **"Tài khoản bị tạm khóa 15 phút do nhập sai mật khẩu xác minh 5 lần"** | Admin nhập sai mật khẩu đăng nhập quá 5 lần khi mở cổng xem mật khẩu (Reveal Gate). | Chờ đủ 15 phút để hệ thống tự động mở khóa, hoặc nhờ tài khoản Admin khác hỗ trợ. |
| **"Mã nhân viên không đúng định dạng chuẩn TVC"** | Mã nhân viên nhập sai định dạng quy định của công ty. | Nhập mã có tiền tố `TVC` theo sau là các chữ số (Ví dụ: `TVC00015`). |

---

*Tài liệu được ban hành và bảo trì bởi Bộ phận CNTT - Công ty TNHH Tokuyama Việt Nam.*  
*Mọi thắc mắc và yêu cầu hỗ trợ kỹ thuật, vui lòng liên hệ trực tiếp Quản trị viên IT phụ trách.*
