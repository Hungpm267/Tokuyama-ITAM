# Tokuyama Vietnam — IT Asset Management (ITAM)

Hệ thống Web nội bộ quản lý toàn diện vòng đời tài sản CNTT, bản quyền phần mềm, thẻ từ ra vào, hợp đồng mua sắm và danh bạ thoại cho **Công ty TNHH Tokuyama Việt Nam**, thay thế hoàn toàn các file Excel quản lý thủ công trước đây.

Giao diện hỗ trợ song song 3 ngôn ngữ theo thời gian thực: **Tiếng Việt (`VI`)**, **English (`EN`)**, và **日本語 (`JA`)**.

---

## Mục lục

1. [Phân quyền Người dùng & Đăng nhập](#1-phân-quyền-người-dùng--đăng-nhập)
2. [Giao diện & Tìm kiếm Toàn cục (Ctrl + K)](#2-giao-diện--tìm-kiếm-toàn-cục-ctrl--k)
3. [Nghiệp vụ 1: Quản lý Tài sản Phần cứng & Bàn giao (Hardware Assets)](#3-nghiệp-vụ-1-quản-lý-tài-sản-phần-cứng--bàn-giao-hardware-assets)
4. [Nghiệp vụ 2: Quản lý Nhân sự & Kho Mật khẩu (Secret Vault)](#4-nghiệp-vụ-2-quản-lý-nhân-sự--kho-mật-khẩu-secret-vault)
5. [Nghiệp vụ 3: Quản lý Bản quyền Phần mềm (Software Licenses)](#5-nghiệp-vụ-3-quản-lý-bản-quyền-phần-mềm-software-licenses)
6. [Nghiệp vụ 4: Quản lý Thẻ Từ Ra Vào & Mượn-Trả (Access Cards)](#6-nghiệp-vụ-4-quản-lý-thẻ-từ-ra-vào--mượn-trả-access-cards)
7. [Nghiệp vụ 5: Hợp đồng Mua sắm IT (Contracts & Procurement)](#7-nghiệp-vụ-5-hợp-đồng-mua-sắm-it-contracts--procurement)
8. [Nghiệp vụ 6: Danh bạ Điện thoại Nội bộ (Phone Directory)](#8-nghiệp-vụ-6-danh-bạ-điện-thoại-nội-bộ-phone-directory)
9. [Nghiệp vụ 7: Thùng rác & Khôi phục Dữ liệu (Trash & Recovery)](#9-nghiệp-vụ-7-thùng-rác--khôi-phục-dữ-liệu-trash--recovery)
10. [Nghiệp vụ 8: Phân quyền RBAC & Nhật ký Kiểm toán (Audit Trail)](#10-nghiệp-vụ-8-phân-quyền-rbac--nhật-ký-kiểm-toán-audit-trail)
11. [Xử lý Sự cố Nghiệp vụ Thường gặp (FAQ)](#11-xử-lý-sự-cố-nghiệp-vụ-thường-gặp-faq)

---

## 1. Phân quyền Người dùng & Đăng nhập

Hệ thống được thiết kế phục vụ 3 nhóm đối tượng chính với thẩm quyền chặt chẽ (RBAC):

| Vai trò (Role) | Đối tượng sử dụng | Phạm vi thẩm quyền trên hệ thống |
| :--- | :--- | :--- |
| **Quản trị viên IT** (`ADMIN`) | 1 IT phụ trách | Toàn quyền quản trị tất cả các phân hệ: thêm/sửa/xóa tài sản, cấu hình người dùng, phân quyền RBAC, xem kho mật khẩu nhân viên (Secret Vault), khôi phục dữ liệu từ Thùng rác. |
| **Trưởng phòng GA** (`GA_MANAGER`) | 1 Trưởng phòng Tổng vụ | Quản lý danh mục tài sản, thực hiện bàn giao/thu hồi máy tính, cho mượn/trả thẻ từ ra vào, theo dõi tiến độ hợp đồng mua sắm IT, danh bạ thoại. *Không có quyền truy cập kho mật khẩu nhân viên.* |
| **Ban Giám đốc** (`EXECUTIVE`) | 3 Giám đốc người Nhật | Quyền xem dữ liệu báo cáo (Read-only) trên các bảng danh sách: Tài sản phần cứng, License phần mềm, Hợp đồng, Thẻ từ, Nhật ký kiểm toán. |

### Đăng nhập & Đổi ngôn ngữ
1. **Truy cập:** Mở trình duyệt truy cập đường dẫn `/admin` (hoặc `/login`).
2. **Đăng nhập:** Nhập `Username` và `Password` đã được cấp.
3. **Đổi ngôn ngữ:** Nhấp vào nút chọn ngôn ngữ tại góc trên bên phải màn hình (`VI` / `EN` / `JA`) để chuyển đổi tức thì toàn bộ nhãn, tiêu đề, trạng thái và thông báo.

---

## 2. Giao diện & Tìm kiếm Toàn cục (Ctrl + K)

- **Menu điều hướng bên trái (Sidebar):** Được phân nhóm logic:
  - *Hệ thống & Phân quyền:* Người dùng, Vai trò, Ma trận Quyền.
  - *Danh mục Dùng chung:* Phòng ban, Loại thiết bị, Nhãn (Tags), Vị trí/Phòng.
  - *Nghiệp vụ cốt lõi:* Nhân sự, Kho Mật khẩu, Tài sản IT, License, Thẻ từ, Hợp đồng, Danh bạ thoại.
  - *Giám sát & An toàn:* Thùng rác, Nhật ký Kiểm toán (Audit Trail).
- **Tìm kiếm toàn cục (`Ctrl + K`):** Bấm phím nóng `Ctrl + K` (hoặc click vào ô tìm kiếm trên thanh tiêu đề) để tra cứu nhanh đa phân hệ:
  - Mã tem GA (ví dụ: `GA-LAP-001`)
  - Số Serial máy tính (ví dụ: `PF3Z9X11`)
  - Địa chỉ MAC mạng (LAN / Wifi)
  - Mã nhân viên (ví dụ: `TVC00012`) hoặc Tên nhân viên
  - Số thẻ từ ra vào, Số hợp đồng mua sắm, Số máy nhánh điện thoại.

---

## 3. Nghiệp vụ 1: Quản lý Tài sản Phần cứng & Bàn giao (Hardware Assets)

### 3.1. Vòng đời Trạng thái Thiết bị
- `IN_STOCK` (Trong kho / 在庫): Thiết bị sẵn sàng để bàn giao cho nhân viên.
- `IN_USE` (Đang sử dụng / 使用中): Máy đang được cấp phát cho một nhân viên cụ thể.
- `REPAIR` (Đang sửa chữa / 修理中): Thiết bị đang hỏng hóc, gửi bảo hành hoặc chờ sửa.
- `DISPOSED` (Đã thanh lý / 廃棄済み): Thiết bị cũ hỏng đã hủy hoặc bán thanh lý.
- `LOST` (Bị mất / 紛失): Thiết bị thất lạc.

### 3.2. Quy trình Bàn giao Thiết bị (Assign)
> **Quy tắc bất biến:** Mỗi thiết bị chỉ được có tối đa **MỘT** lượt bàn giao đang mở (`returned_at IS NULL`). Không thể bàn giao thiết bị đang có người dùng.

1. Tại danh sách thiết bị (`/admin/asset/list`), bấm nút **Bàn giao** (biểu tượng bắt tay 🤝) tại dòng máy có trạng thái `IN_STOCK`.
2. Chọn **Nhân viên nhận máy** từ danh bạ (tìm theo Mã NV hoặc Tên).
3. Chọn **Ngày bàn giao** (mặc định là hôm nay) và nhập ghi chú phụ kiện (sạc, chuột, túi xách...).
4. Nhấn **Xác nhận bàn giao**. Hệ thống sẽ:
   - Chuyển trạng thái máy sang `IN_USE`.
   - Cập nhật tên người đang giữ máy trên danh sách.
   - Ghi lại lịch sử bàn giao và nhật ký kiểm toán.

### 3.3. Quy trình Thu hồi Thiết bị (Return)
1. Bấm nút **Thu hồi** (biểu tượng mũi tên quay lại ↩️) tại dòng máy đang `IN_USE`.
2. Chọn **Ngày thu hồi** (hệ thống kiểm tra `Ngày thu hồi >= Ngày bàn giao`).
3. Chọn trạng thái sau thu hồi: **Nhập lại kho** (`IN_STOCK`) hoặc **Đưa đi sửa chữa** (`REPAIR`).
4. Nhập ghi chú hiện trạng máy khi nhận lại.
5. Xác nhận: Lịch sử cũ được chốt ngày kết thúc, thiết bị sẵn sàng cấp phát tiếp.

### 3.4. Nhập kho theo lô từ Hợp đồng (Batch Receive)
Khi công ty nhập về lô 10–50 máy tính mới:
1. Bấm nút **Nhập kho theo lô** (`Batch Receive`) trên thanh công cụ trang Tài sản.
2. Chọn **Hợp đồng & Hạng mục hợp đồng** liên kết (Contract Line).
3. Chọn cấu hình chung (Loại thiết bị, Model, CPU, RAM, Ổ cứng...).
4. Dán bảng danh sách từ Excel (Mã tem GA, Số Serial, MAC LAN, MAC Wifi).
5. Bấm **Tiến hành nhập kho**: Toàn bộ máy được tạo tự động, kiểm tra chống trùng serial, và tự động cập nhật số lượng đã nhận của Hợp đồng.

---

## 4. Nghiệp vụ 2: Quản lý Nhân sự & Kho Mật khẩu (Secret Vault)

### 4.1. Hồ sơ Nhân viên (`/admin/person/list`)
- Quản lý mã nhân viên (định dạng chuẩn `TVCxxxxx`), họ tên, phòng ban, email, ngày vào làm và tình trạng công tác (`ACTIVE`, `SCHEDULED`, `RESIGNED`).
- Trang chi tiết nhân sự hiển thị đầy đủ: Các máy tính đang giữ, các license đang dùng và thẻ ra vào đang mượn.

### 4.2. Kho Mật khẩu Nhân viên (`/admin/person-secret/list`) — Chuẩn Bảo mật FR-06
Hệ thống hỗ trợ lưu mật khẩu PC và Email của nhân viên để phục vụ công tác bàn giao và xử lý sự cố nội bộ. Cơ chế bảo mật được thiết kế tuyệt đối:

- **Mã hóa phần cứng AES-256-GCM:** Mật khẩu được mã hóa an toàn với khóa riêng trong máy chủ.
- **Mặc định che giấu:** Màn hình luôn hiển thị dấu chấm `••••••` để chống nhìn trộm màn hình.
- **Quy trình Mở khóa 2 lớp (Reveal Gate):**
  1. Chỉ tài khoản Quản trị viên (`ADMIN`) mới có nút **Xem**.
  2. Bấm "Xem" → Bắt buộc **nhập lại chính mật khẩu đăng nhập của Admin**.
  3. Đúng mật khẩu → Hệ thống cấp token xác thực tạm thời trong **2 phút**.
  4. Mật khẩu giải mã hiển thị trên modal kèm đồng hồ đếm ngược.
  5. **Tự động xóa sạch sau 60 giây**: Modal tự đóng và xóa sạch mật khẩu khỏi bộ nhớ màn hình.
  6. Khi đóng modal (bằng nút X, phím ESC hoặc click ra ngoài), mật khẩu trong HTML bị xóa ngay lập tức về `••••••`.
  7. **Khóa an toàn:** Nếu nhập sai mật khẩu xác minh 5 lần trong 15 phút, tài khoản Admin sẽ bị tạm khóa tính năng xem trong 15 phút.
  8. Mỗi lượt xem đều ghi nhận một dòng nhật ký kiểm toán hành động `REVEAL`.
- **Nút "Khóa phiên" (Lock):** Trên thanh công cụ có nút màu đỏ cho phép Admin hủy ngay lập tức phiên xem mật khẩu khi rời khỏi bàn làm việc.

---

## 5. Nghiệp vụ 3: Quản lý Bản quyền Phần mềm (Software Licenses)

### 5.1. Danh mục Phần mềm & Kho License
- **Sản phẩm phần mềm (`LicenseProduct`):** Quản lý tên phần mềm (Microsoft 365, AutoCAD, Windows 11...), hãng sản xuất, loại bản quyền (`PER_DEVICE`, `PER_USER`, `SITE`).
- **Kho Bản quyền (`License`):** Quản lý từng gói key mua về: Ngày kích hoạt, ngày hết hạn, hợp đồng liên kết và tổng số lượng bản quyền (**Total Seats**). Khóa bản quyền (`license_key`) được mã hóa an toàn.

### 5.2. Cấp phát License & Chống Vượt định mức (Seat Limits)
- Gán license cho máy tính hoặc trực tiếp cho nhân viên.
- Hệ thống tự động tính toán:
  $$\text{Còn trống (Remaining Seats)} = \text{Tổng số (Seats)} - \text{Đang cấp phát (Active Assignments)}$$
- **Chống cấp phát vượt hạn mức:** Khi số bản quyền còn trống bằng 0, hệ thống tự động khóa chức năng gán và hiển thị cảnh báo *"Hết chỗ"*.
- **Thu hồi:** Khi nhân viên nghỉ việc hoặc máy tính thu hồi, bấm **Thu hồi License** để hoàn trả lại số ghế trống cho kho.

---

## 6. Nghiệp vụ 4: Quản lý Thẻ Từ Ra Vào & Mượn-Trả (Access Cards)

### 6.1. Danh mục Thẻ từ
- Quản lý mã số thẻ in trên vỏ, loại thẻ:
  - `STAFF`: Thẻ nhân viên chính thức.
  - `CONTRACTOR`: Thẻ phát cho nhà thầu thi công, đối tác kỹ thuật vào nhà máy ngắn ngày.
  - `GUEST`: Thẻ cho khách tham quan văn phòng.
- Trạng thái thẻ: `IN_STOCK` (Sẵn sàng trong tủ), `BORROWED` (Đang cho mượn), `LOST` (Bị mất), `DAMAGED` (Hỏng).

### 6.2. Sổ Mượn - Trả Thẻ (`CardLoan`)
- Cho phép mượn thẻ linh hoạt:
  - Mượn cho **Nhân viên nội bộ**: Chọn nhân viên từ danh sách.
  - Mượn cho **Nhà thầu ngoài**: Nhập họ tên đối tác và tên công ty (ví dụ: *Yamada Taro - Tokyo Systems*).
- Ghi nhận ngày mượn, ngày hẹn trả và mục đích vào nhà máy.
- Hệ thống chặn không cho mượn một thẻ đang có trạng thái `BORROWED`. Khi nhận lại thẻ, bấm **Trả thẻ** để đưa thẻ về trạng thái sẵn sàng.

---

## 7. Nghiệp vụ 5: Hợp đồng Mua sắm IT (Contracts & Procurement)

### 7.1. Quản lý Hợp đồng & Hạng mục mua sắm
- Quản lý số hợp đồng, nhà cung cấp (Dell, FPT, KDDI...), ngày ký kết và ghi chú.
- Mỗi hợp đồng gồm các hạng mục mua sắm chi tiết (Contract Lines) như: Số lượng đặt mua, thông số kỹ thuật.

### 7.2. Tự động tính toán Tiến độ Giao hàng (Delivery Progress)
> **Quy tắc bất biến:** Không cho phép gõ tay số lượng đã nhận. Số lượng nhận hàng được đếm tự động 100% từ số máy thực tế có gắn mã hợp đồng trong hệ thống.

Hệ thống tự động hiển thị huy hiệu tiến độ:
- **Chưa nhận (`PENDING`):** Số lượng đã nhận = 0.
- **Giao một phần (`PARTIAL`):** Đã nhận một phần số lượng đặt mua.
- **Đã đủ hàng (`COMPLETED`):** Đã nhận đủ 100% số lượng đặt mua.

---

## 8. Nghiệp vụ 6: Danh bạ Điện thoại Nội bộ (Phone Directory)

- Quản lý danh bạ máy nhánh nội bộ (số Extension), thiết bị thoại (IP Phone, DECT Station, PBX), địa chỉ IP, vị trí phòng ban và nhân viên trực máy.
- Giúp nhân viên và bộ phận lễ tân/GA tra cứu nhanh đầu số liên lạc nội bộ trong nhà máy và văn phòng.

---

## 9. Nghiệp vụ 7: Thùng rác & Khôi phục Dữ liệu (Trash & Recovery)

### 9.1. Cơ chế Xóa mềm (Soft-Delete)
- Khi xóa bất kỳ bản ghi nào (Thiết bị, Nhân viên, Hợp đồng, Thẻ...), dữ liệu **không bao giờ bị mất vĩnh viễn** mà được đánh dấu `is_deleted = true`.
- **Bắt buộc nhập lý do xóa:** Hệ thống yêu cầu người xóa phải nhập lý do cụ thể để đảm bảo tính minh bạch kiểm toán.

### 9.2. Khôi phục từ Thùng rác (`/admin/trash`)
- Chỉ Quản trị viên (`ADMIN`) có quyền truy cập trang Thùng rác.
- Cho phép lọc theo từng danh mục (Tài sản, Nhân sự, Thẻ từ, Hợp đồng...).
- Bấm nút **Khôi phục (`Restore` / `復元`)**: Hệ thống tự động kiểm tra tính hợp lệ của số Serial/Mã số và đưa bản ghi trở lại hoạt động bình thường, đồng thời ghi lại nhật ký `RESTORE`.

---

## 10. Nghiệp vụ 8: Phân quyền RBAC & Nhật ký Kiểm toán (Audit Trail)

### 10.1. Ma trận Phân quyền Trực quan (`/admin/role-permission/list`)
- Admin có thể xem và bật/tắt quyền hạn giữa các **Vai trò** và các **Phân hệ** theo 4 quyền: `View` (Xem), `Add` (Thêm), `Change` (Sửa), `Delete` (Xóa).
- Có nút **Lưu ma trận** và nút **Khôi phục mặc định** (`Reset to Defaults`) để hoàn nguyên quyền hạn chuẩn theo quy định ban đầu.

### 10.2. Nhật ký Kiểm toán Bất biến (`/admin/audit-log/list`)
> **Bảo vệ chống gian lận:** Bảng `audit_logs` có Trigger khóa cứng ở tầng Database PostgreSQL. Ngay cả người có chuỗi kết nối trực tiếp vào Database cũng **tuyệt đối không thể SỬA (UPDATE) hay XÓA (DELETE)** nhật ký.

- Ghi vết tự động cho mọi hành vi: `CREATE`, `UPDATE`, `DELETE`, `RESTORE`, `LOGIN`, `LOGIN_FAIL`, `REVEAL`.
- Lưu rõ: Ai thực hiện, làm trên bảng nào, mã bản ghi là gì, từ địa chỉ IP nào, thời điểm nào và chi tiết dữ liệu thay đổi trước/sau.
- Toàn bộ trường nhạy cảm (mật khẩu băm, mật khẩu mã hóa) đều được tự động ẩn `[REDACTED]` trước khi lưu nhật ký.

---

## 11. Xử lý Sự cố Nghiệp vụ Thường gặp (FAQ)

| Tình huống / Thông báo lỗi | Nguyên nhân | Hướng xử lý |
| :--- | :--- | :--- |
| **"Thiết bị này hiện đang được bàn giao cho nhân viên khác sử dụng (chưa thu hồi)"** | Thiết bị đang có 1 phiếu cấp phát chưa chốt ngày trả. | Vào Lịch sử cấp phát của máy đó, thực hiện **Thu hồi (`Return`)** trước khi bàn giao cho người mới. |
| **"Số Serial này đã tồn tại trong hệ thống (bị trùng lặp)"** | Máy tính có serial này đã được tạo trước đó hoặc đang nằm trong Thùng rác. | Kiểm tra lại số serial hoặc vào **Thùng rác (`/admin/trash`)** để khôi phục thay vì tạo mới. |
| **"Bản quyền này đã hết lượt gán (0 seats remaining)"** | Toàn bộ số lượng bản quyền mua đã được gán hết cho nhân viên/thiết bị. | Kiểm tra danh sách gán để thu hồi từ máy không dùng, hoặc liên hệ GA lập hợp đồng mua thêm bản quyền. |
| **"Tài khoản bị tạm khóa 15 phút do nhập sai mật khẩu xác minh 5 lần"** | Admin nhập sai mật khẩu xác nhận quá 5 lần khi mở cổng xem mật khẩu (Reveal Gate). | Chờ đủ 15 phút để hệ thống tự động mở khóa, hoặc nhờ tài khoản Admin khác hỗ trợ. |
| **"Mã nhân viên không đúng định dạng chuẩn TVC"** | Mã nhân viên nhập sai định dạng quy định của công ty. | Nhập mã có tiền tố `TVC` theo sau là các chữ số (Ví dụ: `TVC00015`). |
| **Không tìm thấy thẻ từ trong danh sách cho mượn** | Thẻ đang được cho người khác mượn hoặc đang ở trạng thái Báo mất/Hỏng. | Kiểm tra sổ mượn thẻ để thu hồi thẻ trước, hoặc kiểm tra lại trạng thái của thẻ. |

---

*Tài liệu hướng dẫn nghiệp vụ — Hệ thống Quản trị Tài sản IT Công ty TNHH Tokuyama Việt Nam.*  
*Mọi thắc mắc và hỗ trợ kỹ thuật, vui lòng liên hệ Quản trị viên IT phụ trách.*
