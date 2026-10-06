---
title: Hệ thống Quản lý Tài sản IT – Tokuyama Vietnam. Tài liệu Yêu cầu & Kế hoạch (BRD) v2
tags: [IT process]
---

# Hệ thống Quản lý Tài sản IT – Tokuyama Vietnam: Tài liệu Yêu cầu & Kế hoạch (BRD)

**Phiên bản 2.0** · Oct 6, 2026 · @AJ Pham

> **Thay đổi so với v1 (05/10/2026):** đổi backend từ Django sang FastAPI; bổ sung module Phone List; chốt lưu mật khẩu PC/email có mã hóa kèm cơ chế xác minh lại khi xem; mở rộng mô hình dữ liệu từ 15 lên 23 bảng; thêm nhãn thiết bị (Zscaler/MES) thay cho cột cứng; tách mã vendor và mã tem GA; hai địa chỉ MAC. Chi tiết ở mục "Nhật ký quyết định".

## Tóm tắt dự án

Dự án xây một web app nội bộ bằng FastAPI + PostgreSQL, thay thế toàn bộ các file Excel quản lý thiết bị, license, thẻ ra vào, danh bạ máy nhánh và tình trạng giao hàng theo mã hợp đồng. Mục tiêu là một nguồn dữ liệu duy nhất (SSOT) cho IT và GA. Tài liệu đang ở giai đoạn đặc tả yêu cầu và thiết kế (vai trò BA / Solution Architect).

| Hạng mục | Nội dung |
| --- | --- |
| Tên dự án | Hệ thống Quản lý Tài sản IT (IT Asset Management – ITAM) |
| Đơn vị | Tokuyama Vietnam (TVC) |
| Chủ dự án, developer, người bảo trì | IT (người duy nhất của bộ phận IT) |
| Người dùng | 1 IT, 1 trưởng GA, 3 giám đốc người Nhật (tổng 5) |
| Công nghệ | FastAPI + SQLAlchemy + Alembic + PostgreSQL, giao diện render phía server (Jinja2) |
| Chuyển đổi dữ liệu | Nhập tay toàn bộ bởi IT, sau đó ngừng dùng Excel |
| Ngoài phạm vi đợt này | Hệ thống cảnh báo tự động, giao diện điện thoại, quét QR |
| Giai đoạn hiện tại | Đặc tả yêu cầu và thiết kế cơ sở dữ liệu |

## Hiện trạng và painpoint

Thông tin tài sản IT đang nằm rải rác ở nhiều file và sheet Excel không liên kết. Hậu quả là dữ liệu trùng lặp, lệch nhau, không ai biết hạn và lộ thông tin nhạy cảm. Bảng dưới là bằng chứng lấy từ chính các file hiện tại.

| Nguồn hiện tại | Đang quản lý | Vấn đề quan sát được |
| --- | --- | --- |
| Sheet "2026" (list of TVC employees) | Nhân viên, PC Name, GA code, tài khoản, 6 cột license, trạng thái giao, model, S/N | Lưu mật khẩu PC và email dạng chữ thường; mỗi phần mềm là một cột riêng, mua thêm phần mềm phải chèn cột; màu dòng mang nghĩa ngầm (Zscaler / MES) không được ghi lại thành dữ liệu; trạng thái là chữ tự do, có lỗi chính tả; ngày hiện dạng số serial (46022) |
| Sheet "PC_Serial Number" | Serial PC và màn hình theo số báo giá KHCM | Trùng với cột S/N của sheet "2026", phải sửa tay hai nơi |
| Sheet "PC_Qty summary" | Số lượng mua, đã giao, đang cài đặt, còn lại | Nhập tay, ghi "update by Aug 11th" nên có thể đã cũ |
| Sheet "Trendmicro" | PC, PC username, active status, expire date. 13 license, 5 đang dùng | 3/5 license đang dùng không có ngày hết hạn; hạn ghi theo từng máy chứ không theo gói mua |
| File 返却管理 (thẻ ra vào) | Thẻ cho nhà thầu mượn, quyền vào phòng | Thẻ mượn từ tháng 6–7/2026 vẫn trống ngày trả; định dạng ngày lẫn lộn (29/09/2026 và 29/9/2026); quyền vào phòng ghi dạng câu tiếng Nhật ("倉庫のみ入退室許可", "Document Room, Server Room, Master Room 以外") không lọc được |
| File Phone List | 52 thiết bị thoại: location (building/floor/room), device type, device name, extension number | Tên phòng gõ tay, sai chính tả có hệ thống: "Offce Room" (5 dòng), "Analysys Room", "Sound side of process buiding"; extension "N/A" lẫn với số thật |
| File hợp đồng KDDI, license IJCAD/PDF/Office | Hợp đồng, license | Không liên kết với thiết bị hay người dùng |

**Painpoint chính:**

1. **Phân mảnh:** muốn biết "nhân viên A đang giữ gì" phải mở nhiều file.
2. **Trùng lặp và lệch dữ liệu:** cùng một serial được nhập ở nhiều nơi.
3. **Không có lịch sử:** không biết thiết bị đã qua tay những ai.
4. **Dễ quên:** không thấy license sắp hết hạn hay thẻ chưa trả.
5. **Rủi ro bảo mật:** mật khẩu nằm trong file dùng chung, ai mở được file là đọc được.
6. **Không mở rộng được:** thêm một phần mềm hay một nhãn máy mới là phải sửa cấu trúc file.

## Mục tiêu và chỉ số thành công

Dự án thành công khi toàn bộ file Excel liên quan được ngừng dùng và mọi tra cứu tài sản đều làm được trên app.

| Mục tiêu | Chỉ số đo | Ngưỡng đạt |
| --- | --- | --- |
| Một nguồn dữ liệu duy nhất | Số file Excel quản lý tài sản còn được cập nhật | 0 sau ngày cut-over |
| Tra cứu nhanh | Thời gian trả lời "thiết bị X đang ở đâu, ai giữ" | Dưới 30 giây |
| Không mất dấu | Thiết bị, license, thẻ có lịch sử đầy đủ người giữ | 100% bản ghi tạo sau go-live |
| Không quên hạn | License có ngày hết hạn hoặc ghi rõ vĩnh viễn | 100% |
| Bảo mật mật khẩu | Mật khẩu lưu dạng mã hóa, mọi lần xem đều có log | 100%; 0 mật khẩu còn nằm trong file Excel dùng chung |
| Mở rộng không sửa cấu trúc | Thêm một phần mềm / một nhãn máy mới | Chỉ thêm bản ghi, không chạy migration |

## Phạm vi và người dùng

Đợt 1 gồm 7 module nghiệp vụ, dùng trên trình duyệt máy tính. Cảnh báo tự động và giao diện điện thoại để dành cho các đợt sau. Người dùng hệ thống chỉ có 5 người, còn toàn bộ nhân viên là đối tượng dữ liệu, không đăng nhập.

| Module | Nội dung | Đợt |
| --- | --- | --- |
| Nhân sự | Danh mục nhân viên (mã TVC, user ID, email, phòng ban, trạng thái làm việc) và kho mật khẩu có mã hóa | 1 |
| Tài sản | Laptop, màn hình, điện thoại, chuột, phụ kiện: mã GA, mã vendor, model, serial, HWID, 2 MAC, nhãn, trạng thái | 1 |
| Mượn – trả thiết bị | Cho nhân viên mượn thiết bị, nhận trả, lịch sử đầy đủ | 1 |
| License | IJCAD, Office LTSC, PDF, Trend Micro, MS365, Visio, Windows: số lượng, gán cho máy/người, ngày hết hạn | 1 |
| Thẻ ra vào | Thẻ, phòng được phép vào, ai mượn, ngày mượn/hẹn trả/trả thực tế | 1 |
| Hợp đồng | Mã hợp đồng (KHCM-…), dòng hàng và số lượng đặt, số đã nhận tự tính, tình trạng giao | 1 |
| **Phone List** | Danh bạ máy nhánh: thiết bị thoại, loại, số extension, vị trí | **1 (làm sau cùng)** |
| Cảnh báo email/Teams | Tự nhắc license hết hạn, thẻ quá hạn | Sau |
| Giao diện điện thoại, quét QR | Kiểm kê bằng điện thoại | Sau |

**Vì sao Phone List vào đợt 1.** Đây là module đơn giản nhất trong toàn hệ thống: hai bảng, không có giao dịch, không có lịch sử mượn trả, không phụ thuộc Person hay Asset. 52 dòng dữ liệu nhập trong khoảng một giờ. Nó dùng chung bảng `locations` với module Thẻ ra vào, nên nếu để lại đợt sau thì bảng `locations` vẫn phải thiết kế ngay từ đầu — tức là đã trả gần hết chi phí mà không thu được lợi ích. Xếp làm sau cùng trong đợt 1 để không cạnh tranh thời gian với các module lõi.

**Ngoài phạm vi:** quản lý nhân sự nhà thầu, lưu nội dung hợp đồng (giá, điều khoản, file đính kèm), tự động quét thiết bị qua Intune/AD, quy trình phê duyệt mua sắm, cổng để nhân viên tự gửi yêu cầu, quản lý IP/VLAN.

| Người dùng | Vai trò trong hệ thống | Mục đích chính |
| --- | --- | --- |
| IT | Admin | Nhập liệu, quản lý tài sản/license, xem mật khẩu, quản lý người dùng và quyền |
| Trưởng GA | GA Manager | Quản lý thẻ ra vào, tra cứu tài sản và nhân sự |
| 3 giám đốc người Nhật | Executive | Xem tổng quan, tra cứu, xem hợp đồng |

## Phân quyền RBAC và bảo mật

### Vì sao RBAC phải tự xây

Với Django, phân quyền Đọc/Ghi/Sửa/Xóa có sẵn qua `Group` và `Permission`. FastAPI không có gì tương đương, nên đây trở thành một hạng mục phát triển thật sự với 4 bảng và một lớp dependency kiểm tra quyền trên mọi endpoint. Thiết kế dưới đây cố ý giữ mô hình giống Django để không phát minh lại khái niệm.

**Mô hình:** mỗi người dùng thuộc đúng một vai trò. Vai trò nắm một tập quyền dạng `(module, action)` với action ∈ {view, add, change, delete}. Ngoài ra Admin có thể cấp hoặc thu hồi quyền lẻ cho một người dùng cụ thể qua bảng override, không cần đổi vai trò và không cần sửa code.

Ký hiệu: Đ = đọc, G = ghi (thêm mới), S = sửa, X = xóa (xóa mềm).

| Module | Admin (IT) | GA Manager | Executive |
| --- | --- | --- | --- |
| Nhân sự | Đ G S X | Đ G S | Đ |
| **Mật khẩu nhân viên (xem giá trị thật)** | **Đ** | — | — |
| Tài sản | Đ G S X | Đ | Đ |
| Mượn – trả thiết bị | Đ G S X | Đ | Đ |
| License (key bị che) | Đ G S X | — | Đ |
| Thẻ ra vào | Đ G S X | Đ G S X | Đ |
| Hợp đồng | Đ G S X | Đ | Đ |
| Phone List | Đ G S X | Đ G S | Đ |
| Nhật ký thay đổi (audit log) | Đ | — | Đ |
| Thùng rác (khôi phục bản ghi đã xóa) | Đ S | — | — |
| Quản lý người dùng & vai trò | Đ G S X | — | — |

Bảng trên là cấu hình mặc định, nằm trong dữ liệu seed chứ không nằm trong code. Quyền "xem mật khẩu" là một quyền riêng, tách khỏi quyền đọc module Nhân sự — người có quyền đọc hồ sơ nhân viên vẫn chỉ thấy dấu sao.

### Quy tắc bảo mật

- **Đăng nhập:** tài khoản nội bộ, mật khẩu băm bằng **Argon2id** (hoặc bcrypt cost ≥ 12). Phiên làm việc dùng cookie `HttpOnly` + `SameSite=Lax`, tự đăng xuất sau 30 phút không thao tác. SSO bằng Microsoft Entra ID (kèm MFA, qua `authlib` OIDC) làm khi chuyển lên máy chủ công ty, vì Entra ID cần HTTPS và tên miền cố định.
- **Audit log:** mọi thao tác thêm/sửa/xóa/khôi phục/đăng nhập/xem mật khẩu đều ghi ai, lúc nào, bản ghi nào, giá trị trước và sau. Không ai sửa hay xóa được audit log, kể cả Admin — quyền DB của tài khoản ứng dụng trên bảng này chỉ có `INSERT` và `SELECT`.
- **Che dữ liệu nhạy cảm:** license key và mật khẩu nhân viên luôn hiển thị dạng `••••••` ở mọi màn hình và mọi API trả về danh sách.
- **Khi IT vắng mặt:** README, bản `pg_dump` mới nhất và **khóa mã hóa cất riêng** (xem dưới) đủ để người khác dựng lại app trên một máy khác.
- **Đợt 1** truy cập qua HTTP trong LAN; bật HTTPS khi lên máy chủ công ty.

### Lưu và xem mật khẩu nhân viên

Đây là hạng mục nhạy cảm nhất của hệ thống. Quyết định là **có lưu**, với thiết kế sau.

**Lưu trữ**

- Mật khẩu PC và mật khẩu email nằm ở **bảng riêng** `person_secrets`, không nằm trong bảng `persons`. Mục đích: một câu `SELECT * FROM persons` vô tình hay một export CSV sẽ không bao giờ kéo theo mật khẩu.
- Mã hóa **phía ứng dụng** bằng AES-256-GCM (thư viện `cryptography`), mỗi bản ghi một nonce ngẫu nhiên riêng, lưu dạng `BYTEA`. `person_id` được dùng làm associated data để một bản mã không thể bị chép sang người khác.
- **Không dùng `pgcrypto`.** Cơ sở dữ liệu đặt ở dịch vụ cloud bên thứ ba (Neon/Supabase). Với `pgcrypto`, khóa phải đi kèm trong câu SQL, nghĩa là khóa đi qua đường truyền và có thể lọt vào query log của nhà cung cấp. Mã hóa phía ứng dụng bảo đảm nhà cung cấp DB không bao giờ nhìn thấy khóa, và một bản dump bị lộ là một đống byte vô nghĩa.
- **Khóa mã hóa** nạp từ biến môi trường, lấy từ OS keyring của laptop (Windows Credential Manager). Không nằm trong Git, không nằm trong file `.env` được backup. Một bản sao in ra giấy cất trong két của ban giám đốc để phòng trường hợp IT nghỉ việc.
- Mỗi bản ghi lưu kèm `key_version` để đổi khóa về sau mà không phải giải mã lại toàn bộ cùng lúc.
- Trường `note` (ví dụ "mật khẩu thứ hai dùng cho máy MES") lưu dạng thường, vì nó không phải bí mật và cần tìm kiếm được.

**Luồng xem mật khẩu**

1. Người dùng phải có quyền `secrets.view` — chỉ Admin.
2. Màn hình hiển thị `••••••` kèm nút "Xem".
3. Bấm "Xem" mở hộp thoại yêu cầu **nhập lại mật khẩu đăng nhập của chính mình**.
4. Hệ thống xác minh. Đúng thì cấp một **reveal token sống 2 phút** gắn với phiên hiện tại; trong 2 phút đó không phải nhập lại khi xem bản ghi khác.
5. Mật khẩu hiện ra ở dạng chữ, có nút sao chép, và **tự ẩn lại sau 60 giây**.
6. Mỗi lần giải mã thành công ghi một dòng audit `action = REVEAL` với người xem, thời điểm, `person_id`, loại mật khẩu và địa chỉ IP. Dòng này không xóa được.
7. Nhập sai mật khẩu đăng nhập 5 lần trong 15 phút thì khóa chức năng xem trong 15 phút và ghi audit.
8. Giá trị thật chỉ trả về qua một endpoint duy nhất `POST /persons/{id}/secrets/reveal`. Không endpoint nào khác, không màn hình danh sách nào, trả về giá trị giải mã.

**Hai khuyến nghị kèm theo (ngoài phạm vi code, thuộc về vận hành):**

- Mật khẩu email công ty không nên lưu ở đây nếu Microsoft 365 đã có SSO và khôi phục qua Entra ID — IT có thể đặt lại mật khẩu mà không cần biết mật khẩu cũ. Nếu đồng ý, bỏ hẳn cột `email_password_enc` thì giảm được một nửa bề mặt rủi ro.
- Toàn bộ mật khẩu đang nằm trong file Excel dùng chung phải được coi là **đã lộ**. Cần đổi chúng ngay khi nhập sang app, không chờ app xong.

## Yêu cầu chức năng

Đợt 1 có 18 yêu cầu (16 Must, 2 Should). Ưu tiên theo MoSCoW.

| Mã | Yêu cầu | Module | Ưu tiên |
| --- | --- | --- | --- |
| FR-01 | Đăng nhập, đăng xuất, hết phiên sau 30 phút | Hệ thống | Must |
| FR-02 | Admin tạo người dùng, gán vai trò, chỉnh quyền Đ/G/S/X theo vai trò và theo từng người | Hệ thống | Must |
| FR-03 | Kiểm tra quyền trên mọi endpoint; thiếu quyền trả 403 và không lộ dữ liệu trong thông báo lỗi | Hệ thống | Must |
| FR-04 | Tìm kiếm toàn cục theo mã GA, mã vendor, serial, HWID, MAC, tên người, mã hợp đồng, số extension | Hệ thống | Must |
| FR-05 | Thêm/sửa/xóa mềm nhân viên; lưu staff code, user ID, email, ngày vào làm; trạng thái Sắp vào làm / Đang làm / Đã nghỉ | Nhân sự | Must |
| FR-06 | Lưu mật khẩu PC/email dạng mã hóa; hiển thị che; xem phải xác minh lại mật khẩu đăng nhập; ghi audit mỗi lần xem | Nhân sự | Must |
| FR-07 | Thêm/sửa/xóa mềm tài sản; lưu mã GA, mã vendor, model, form factor, serial, HWID, MAC LAN và MAC Wi-Fi | Tài sản | Must |
| FR-08 | Gắn nhãn tự định nghĩa cho tài sản (Zscaler, MES…); thêm nhãn mới không cần sửa cấu trúc | Tài sản | Must |
| FR-09 | Trạng thái tài sản: Trong kho, Đang mượn, Đang sửa, Thanh lý, Mất | Tài sản | Must |
| FR-10 | Cho mượn và nhận trả thiết bị, lưu lịch sử người mượn; chặn cho mượn thiết bị đang có người giữ | Mượn – trả | Must |
| FR-11 | Hồ sơ một người: mọi thiết bị, license, thẻ đang giữ và đã từng giữ | Nhân sự | Must |
| FR-12 | Quản lý license: tổng seat, đã gán, còn trống, ngày hết hạn ở mức gói và ở mức từng lần gán; gán cho máy hoặc người; cảnh báo khi gán vượt số seat | License | Must |
| FR-13 | Cho mượn/trả thẻ ra vào, chọn phòng được phép từ danh mục, ghi mục đích, ngày mượn/hẹn trả/trả thực tế; người mượn là nhân viên hoặc người bên ngoài (ghi tên, công ty) | Thẻ | Must |
| FR-14 | Mã hợp đồng (vd KHCM-2408-0113): dòng hàng và số lượng đặt; số đã nhận **tự tính** từ tài sản gắn vào dòng hợp đồng; hiển thị đã nhận đủ hay chưa và đã giao hay chưa | Hợp đồng | Must |
| FR-15 | Danh bạ máy nhánh: thiết bị thoại, loại, số extension, vị trí (building/floor/room) chọn từ danh mục | Phone List | Must |
| FR-16 | Chuyển ngôn ngữ Anh/Nhật, lưu theo từng người; sáng/tối tự theo hệ điều hành | Hệ thống | Must |
| FR-17 | Trang tổng quan: số thiết bị theo trạng thái, license sắp hết hạn (60 ngày), thẻ đang cho mượn, thẻ quá hạn hẹn trả | Tổng quan | Should |
| FR-18 | Xuất CSV danh sách tài sản, license, thẻ (không bao giờ kèm mật khẩu hay license key) | Hệ thống | Should |

**Ghi chú thiết kế:**

- FR-14 thay thế sheet "PC_Qty summary": số đã nhận không còn gõ tay mà được đếm từ tài sản thực tế. Đây là lý do bảng `contract_lines` **không** có cột `delivered_qty` hay `remaining_qty`.
- FR-12 xử lý đặc thù Trend Micro: sheet hiện tại ghi `expire date` theo từng PC, không theo gói mua. Vì vậy `license_assignments` có `expiry_date` riêng, ghi đè hạn của gói khi cần.
- FR-17 chỉ hiển thị khi mở trang, không gửi thông báo, nên không mâu thuẫn với quyết định chưa làm cảnh báo.
- FR-08 thay cho các cột boolean `has_zscaler`, `is_mes_machine`: đó chính là lỗi "mỗi thuộc tính một cột" mà dự án đang muốn loại bỏ ở phần license.

## Yêu cầu phi chức năng

Phân nhóm theo mô hình chất lượng ISO/IEC 25010. Vì chỉ có một người phát triển và bảo trì, nhóm "Bảo trì" được coi là quan trọng ngang bảo mật.

| Mã | Nhóm | Yêu cầu |
| --- | --- | --- |
| NFR-01 | Đa ngôn ngữ | Giao diện tiếng Anh và tiếng Nhật bằng Babel + Jinja2 gettext; cấu trúc sẵn để thêm tiếng Việt chỉ bằng file dịch. Các bảng danh mục (phòng ban, loại tài sản, phòng, nhãn) có cột `name_en` và `name_ja`; trống `name_ja` thì hiển thị `name_en`. Dữ liệu nhập tay (tên người, ghi chú) không dịch. |
| NFR-02 | Giao diện | Theo hệ điều hành nhờ thẻ meta `color-scheme`; CSS tối thiểu, ưu tiên ra bản dùng được trước. |
| NFR-03 | Tương thích | Chrome và Edge bản mới trên máy tính, màn hình từ 1366px |
| NFR-04 | Hiệu năng | Trang danh sách và tìm kiếm phản hồi dưới 2 giây với 10.000 bản ghi; có index trên mọi cột tìm kiếm ở FR-04 |
| NFR-05 | Bảo mật | Mật khẩu đăng nhập băm Argon2id; mật khẩu nhân viên mã hóa AES-256-GCM phía ứng dụng, khóa ngoài Git; chống CSRF (token trên mọi form) và XSS (Jinja2 autoescape, không dùng `\|safe` với dữ liệu người dùng); truy vấn qua SQLAlchemy ORM, không nối chuỗi SQL; HTTPS và SSO/MFA khi lên máy chủ |
| NFR-06 | Truy vết | Xóa mềm cho mọi bản ghi nghiệp vụ; audit log chỉ thêm, không sửa không xóa, giữ tối thiểu 5 năm |
| NFR-07 | Bảo trì | Code trên Git (repo riêng tư); migration bằng Alembic, không `create_all`; README cài đặt, hướng dẫn backup/khôi phục/đổi khóa mã hóa, mô tả mô hình dữ liệu |
| NFR-08 | Dự phòng | `pg_dump` tự động hằng ngày về máy công ty; kiểm thử khôi phục ít nhất một lần trước go-live |

## Nguyên tắc mô hình dữ liệu và xóa mềm

Dữ liệu xoay quanh ba thực thể gốc là **Person**, **Asset** và **License**. Mọi quan hệ "ai giữ cái gì" được lưu ở bảng giao dịch có ngày bắt đầu/kết thúc, nên lịch sử không bao giờ bị ghi đè.

**Trường chung** trên mọi bảng nghiệp vụ (trừ `audit_logs`): `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`, `deleted_at`, `deleted_by`, `delete_reason`.

**Quy tắc xóa mềm:**

1. Mất, hỏng hay nhân viên nghỉ việc là **trạng thái**, không phải xóa. Xóa mềm chỉ dành cho bản ghi nhập sai hoặc trùng.
2. Bấm "Xóa" chỉ đặt `is_deleted = true` và bắt buộc nhập lý do. Mọi màn hình và truy vấn mặc định ẩn bản ghi đã xóa.
3. Ràng buộc duy nhất (serial, mã tài sản, số thẻ, extension) chỉ áp dụng cho bản ghi chưa xóa, dùng **partial unique index** của PostgreSQL.
4. Chỉ Admin xem được thùng rác và khôi phục bản ghi.
5. Không xóa được tài sản đang mượn hoặc license đang gán; phải thu hồi trước.
6. Bản ghi `assignments`, `license_assignments`, `card_loans`, `audit_logs` không xóa được, chỉ đóng bằng ngày kết thúc.

**Quy tắc toàn vẹn bắt buộc có trong DB, không chỉ trong code.** Đây là nhóm ràng buộc mà thiết kế của Gemini thiếu hoặc làm sai; chúng phải nằm ở tầng database vì tầng ứng dụng sẽ bị bỏ qua khi IT sửa dữ liệu trực tiếp lúc gấp:

| # | Ràng buộc | Cách làm |
| --- | --- | --- |
| 1 | Một thiết bị chỉ được cho mượn một lần tại một thời điểm | `CREATE UNIQUE INDEX ... ON assignments(asset_id) WHERE returned_at IS NULL AND is_deleted = false` |
| 2 | Một thẻ chỉ được cho mượn một lần tại một thời điểm | Partial unique index tương tự trên `card_loans(card_id)` |
| 3 | Một license chỉ gán một lần cho cùng một máy tại một thời điểm | Partial unique index trên `license_assignments(license_id, asset_id) WHERE removed_at IS NULL` |
| 4 | Gán license phải có máy hoặc người | `CHECK (asset_id IS NOT NULL OR person_id IS NOT NULL)` |
| 5 | Mượn thẻ phải có nhân viên hoặc tên người ngoài | `CHECK (person_id IS NOT NULL OR external_name IS NOT NULL)` |
| 6 | Ngày trả không trước ngày mượn | `CHECK (returned_at IS NULL OR returned_at >= borrowed_at)` trên `assignments` và `card_loans` |
| 7 | Ngày hết hạn không trước ngày bắt đầu | `CHECK (expiry_date IS NULL OR start_date IS NULL OR expiry_date >= start_date)` |
| 8 | Mọi giá trị trạng thái nằm trong tập cố định | Kiểu `ENUM` của PostgreSQL (không dùng `VARCHAR` tự do) |
| 9 | Serial, mã GA, số thẻ, extension là duy nhất trong bản ghi sống | Partial unique index `WHERE is_deleted = false` |

> **Lưu ý:** `UNIQUE (asset_id, returned_at)` **không** thay thế được ràng buộc số 1. Trong PostgreSQL `NULL` không bằng `NULL`, nên ràng buộc đó cho phép tạo vô số dòng cấp phát cùng một máy với `returned_at` để trống. Bắt buộc dùng partial unique index.

## Sơ đồ cơ sở dữ liệu (ERD)

Cơ sở dữ liệu có **23 bảng**, chia thành 8 phân hệ. `persons` và `assets` là hai bảng trung tâm.

| Phân hệ | Bảng |
| --- | --- |
| Hệ thống & phân quyền (4) | `users`, `roles`, `role_permissions`, `user_permission_overrides` |
| Danh mục dùng chung (4) | `departments`, `asset_categories`, `asset_tags`, `locations` |
| Nhân sự (2) | `persons`, `person_secrets` |
| Tài sản (3) | `assets`, `asset_tag_links`, `assignments` |
| License (3) | `license_products`, `licenses`, `license_assignments` |
| Thẻ ra vào (3) | `access_cards`, `access_card_locations`, `card_loans` |
| Hợp đồng (2) | `contracts`, `contract_lines` |
| Danh bạ thoại (1) | `phones` |
| Truy vết (1) | `audit_logs` |

Dán đoạn DBML dưới đây vào [dbdiagram.io](https://dbdiagram.io/) để xem sơ đồ.

```dbml
// ==========================================
// TOKUYAMA VIETNAM – IT ASSET MANAGEMENT (SSOT) v2
// 23 bảng. Các cột chung (created_at, created_by, updated_at,
// updated_by, is_deleted, deleted_at, deleted_by, delete_reason)
// được lược bớt khỏi sơ đồ cho dễ nhìn; xem từ điển dữ liệu.
// ==========================================

// ---------- 1. HỆ THỐNG & PHÂN QUYỀN ----------
Table users {
  id int [pk, increment]
  username varchar(50) [unique, not null]
  password_hash text [not null, note: 'Argon2id']
  display_name varchar(100) [not null]
  role_id int [not null]
  preferred_lang varchar(5) [default: 'en', note: 'en | ja']
  is_active boolean [default: true]
  last_login_at timestamptz
  Note: '5 tài khoản đăng nhập hệ thống'
}

Table roles {
  id int [pk, increment]
  code varchar(30) [unique, not null, note: 'ADMIN | GA_MANAGER | EXECUTIVE']
  name_en varchar(100) [not null]
  name_ja varchar(100)
}

Table role_permissions {
  id int [pk, increment]
  role_id int [not null]
  module varchar(40) [not null, note: 'persons, secrets, assets, assignments, licenses, cards, contracts, phones, audit, trash, users']
  action varchar(10) [not null, note: 'view | add | change | delete']
  Note: 'Quyền mặc định theo vai trò. Unique (role_id, module, action)'
}

Table user_permission_overrides {
  id int [pk, increment]
  user_id int [not null]
  module varchar(40) [not null]
  action varchar(10) [not null]
  granted boolean [not null, note: 'true = cấp thêm, false = thu hồi']
  Note: 'Admin chỉnh quyền lẻ cho một người. Unique (user_id, module, action)'
}

// ---------- 2. DANH MỤC DÙNG CHUNG ----------
Table departments {
  id int [pk, increment]
  code varchar(30) [unique]
  name_en varchar(100) [not null]
  name_ja varchar(100)
}

Table asset_categories {
  id int [pk, increment]
  name_en varchar(100) [not null, note: 'Laptop, Monitor, Handy Terminal, Mouse...']
  name_ja varchar(100)
}

Table asset_tags {
  id int [pk, increment]
  code varchar(30) [unique, not null, note: 'ZSCALER | MES | ...']
  name_en varchar(100) [not null]
  name_ja varchar(100)
  color varchar(7) [note: 'Màu hiển thị, thay cho màu ô Excel cũ']
  Note: 'Thay cho các cột boolean has_zscaler / is_mes_machine'
}

Table locations {
  id int [pk, increment]
  building varchar(50) [not null, note: 'Guardhouse, Outside, Office, Factory, Warehouse, External']
  floor varchar(50) [not null, note: 'Security Room, Outside, 1F, 2F']
  room_en varchar(100) [not null, note: 'Server Room, Office Room, Analysis Room...']
  room_ja varchar(100)
  is_access_controlled boolean [default: false, note: 'true = phòng cần thẻ ra vào']
  description text
  Note: 'Danh mục vị trí dùng chung cho Phone List và Thẻ ra vào. Unique (building, floor, room_en)'
}

// ---------- 3. NHÂN SỰ ----------
Table persons {
  id int [pk, increment]
  staff_code varchar(50) [not null, note: 'Mã nhân viên TVC. Duy nhất trên bản ghi sống']
  user_login_id varchar(50) [note: 'User ID hệ thống, vd 57958. Có thể trống với người sắp vào làm']
  full_name varchar(100) [not null]
  department_id int
  email varchar(150)
  status varchar(20) [not null, default: 'ACTIVE', note: 'SCHEDULED | ACTIVE | RESIGNED']
  start_working_date date
  note text
  Note: 'Bảng trung tâm 1. Thay sheet "2026"'
}

Table person_secrets {
  person_id int [pk, note: '1-1 với persons']
  pc_password_enc bytea [note: 'AES-256-GCM, nonce lưu kèm']
  pc_password_note varchar(200) [note: 'Ghi chú không bí mật, vd "mật khẩu cho máy MES"']
  email_password_enc bytea
  email_password_note varchar(200)
  key_version smallint [not null, default: 1]
  Note: 'Bảng riêng để SELECT * trên persons không bao giờ kéo theo mật khẩu'
}

// ---------- 4. TÀI SẢN ----------
Table assets {
  id int [pk, increment]
  asset_code varchar(50) [note: 'Mã tem GA, vd TVC-E00027. Duy nhất trên bản ghi sống']
  vendor_code varchar(50) [note: 'Mã KDDI gán, vd TKY-PC0001. Duy nhất trên bản ghi sống']
  category_id int [not null]
  contract_line_id int [note: 'Trống nếu không thuộc hợp đồng nào']
  model varchar(150) [note: 'Dell Pro 16 (PC16250) XCTO Base']
  form_factor varchar(30) [note: '14inch, 16inch, 24inch']
  serial varchar(100) [note: 'Duy nhất trên bản ghi sống']
  hwid varchar(100)
  mac_ethernet varchar(20)
  mac_wifi varchar(20)
  status varchar(20) [not null, default: 'IN_STOCK', note: 'IN_STOCK | IN_USE | REPAIR | DISPOSED | LOST']
  note text
  Note: 'Bảng trung tâm 2. Mỗi dòng một thiết bị vật lý'
}

Table asset_tag_links {
  asset_id int [not null]
  tag_id int [not null]
  Note: 'PK kép (asset_id, tag_id)'
}

Table assignments {
  id int [pk, increment]
  asset_id int [not null]
  person_id int [not null]
  borrowed_at date [not null]
  returned_at date [note: 'NULL = đang mượn']
  note text
  Note: 'Lịch sử mượn-trả thiết bị. Partial unique index (asset_id) WHERE returned_at IS NULL'
}

// ---------- 5. LICENSE ----------
Table license_products {
  id int [pk, increment]
  name varchar(100) [unique, not null, note: 'Windows, Office LTSC 2024 CSP, IJCAD, Visio, PDF, Trend Micro, MS365']
  vendor varchar(100)
  license_type varchar(30) [note: 'PERPETUAL | SUBSCRIPTION']
}

Table licenses {
  id int [pk, increment]
  product_id int [not null]
  license_key_enc bytea [note: 'Mã hóa như mật khẩu; chỉ Admin xem được']
  key_version smallint [default: 1]
  seats int [not null, default: 1]
  start_date date
  expiry_date date [note: 'NULL = vĩnh viễn']
  contract_id int [note: 'Hợp đồng đã mua gói này; có thể trống']
  note text
  Note: 'Một gói license đã mua'
}

Table license_assignments {
  id int [pk, increment]
  license_id int [not null]
  asset_id int [note: 'Gán theo máy (OEM, Trend Micro)']
  person_id int [note: 'Gán theo người (MS365)']
  assigned_at date [not null]
  expiry_date date [note: 'Hạn riêng của lần gán này, ghi đè hạn của gói. Dùng cho Trend Micro']
  removed_at date [note: 'NULL = đang dùng']
  note text
  Note: 'CHECK (asset_id IS NOT NULL OR person_id IS NOT NULL)'
}

// ---------- 6. THẺ RA VÀO ----------
Table access_cards {
  id int [pk, increment]
  card_no varchar(50) [not null, note: 'Số in trên thẻ. Duy nhất trên bản ghi sống']
  card_type varchar(20) [default: 'CONTRACTOR', note: 'STAFF | CONTRACTOR | GUEST']
  status varchar(20) [default: 'IN_STOCK', note: 'IN_STOCK | BORROWED | LOST | DAMAGED']
  note text
}

Table access_card_locations {
  card_id int [not null]
  location_id int [not null]
  Note: 'Thẻ được vào những phòng nào. PK kép. "Trừ Server/Doc/Master Room" phải quy đổi thành danh sách phòng cụ thể khi nhập'
}

Table card_loans {
  id int [pk, increment]
  card_id int [not null]
  person_id int [note: 'Nhân viên nội bộ mượn; trống nếu người ngoài']
  external_name varchar(100) [note: 'Bắt buộc khi person_id trống']
  external_company varchar(150) [note: 'VD: 倉庫管理業者, 掃除業者']
  purpose text [note: '備考(用途)']
  borrowed_at date [not null, note: '貸出日']
  expected_return_at date
  returned_at date [note: '返却日. NULL = chưa trả']
  Note: 'CHECK (person_id IS NOT NULL OR external_name IS NOT NULL)'
}

// ---------- 7. HỢP ĐỒNG ----------
Table contracts {
  id int [pk, increment]
  code varchar(50) [not null, note: 'KHCM-2510-0130. Duy nhất trên bản ghi sống']
  vendor_name varchar(100) [default: 'KDDI Vietnam']
  signed_date date
  delivery_status varchar(20) [not null, default: 'PENDING', note: 'PENDING | DELIVERED']
  note text
}

Table contract_lines {
  id int [pk, increment]
  contract_id int [not null]
  item_type varchar(100) [not null, note: 'PC 16 inch, PC 14 inch, Monitor...']
  spec text [note: 'Dell Pro 24 Plus QHD USB-C Hub Monitor - P2425DE']
  qty_ordered int [not null]
  Note: 'KHÔNG có delivered_qty / remaining_qty: số đã nhận được ĐẾM từ assets.contract_line_id'
}

// ---------- 8. DANH BẠ THOẠI ----------
Table phones {
  id int [pk, increment]
  device_name varchar(50) [not null, note: 'TELG101, WTSTF101, PBX-MAIN. Duy nhất trên bản ghi sống']
  device_type varchar(30) [not null, note: 'IP_PHONE | DECT_STATION | PBX | WIFI_PHONE']
  extension_number varchar(10) [note: 'NULL thay cho chuỗi "N/A". Duy nhất trên bản ghi sống']
  location_id int
  is_active boolean [default: true]
  remarks text
}

// ---------- 9. TRUY VẾT ----------
Table audit_logs {
  id bigint [pk, increment]
  user_id int [not null]
  created_at timestamptz [not null, default: `now()`]
  table_name varchar(50) [not null]
  record_id int
  action varchar(20) [not null, note: 'CREATE | UPDATE | DELETE | RESTORE | LOGIN | LOGIN_FAIL | REVEAL']
  before_after jsonb [note: 'Giá trị trước và sau. KHÔNG BAO GIỜ chứa mật khẩu hay license key']
  ip_address inet
  Note: 'Chỉ INSERT và SELECT. Không UPDATE, không DELETE, kể cả Admin'
}

// ==========================================
// QUAN HỆ
// ==========================================
Ref: users.role_id > roles.id
Ref: role_permissions.role_id > roles.id
Ref: user_permission_overrides.user_id > users.id

Ref: persons.department_id > departments.id
Ref: person_secrets.person_id - persons.id

Ref: assets.category_id > asset_categories.id
Ref: assets.contract_line_id > contract_lines.id
Ref: asset_tag_links.asset_id > assets.id
Ref: asset_tag_links.tag_id > asset_tags.id

Ref: assignments.asset_id > assets.id
Ref: assignments.person_id > persons.id

Ref: licenses.product_id > license_products.id
Ref: licenses.contract_id > contracts.id
Ref: license_assignments.license_id > licenses.id
Ref: license_assignments.asset_id > assets.id
Ref: license_assignments.person_id > persons.id

Ref: access_card_locations.card_id > access_cards.id
Ref: access_card_locations.location_id > locations.id
Ref: card_loans.card_id > access_cards.id
Ref: card_loans.person_id > persons.id

Ref: contract_lines.contract_id > contracts.id

Ref: phones.location_id > locations.id

Ref: audit_logs.user_id > users.id
```

### Khóa ngoại được phép để trống

| Bảng.cột | Khi nào trống |
| --- | --- |
| `assets.contract_line_id` | Thiết bị không thuộc hợp đồng nào (mua lẻ, thiết bị cũ) |
| `license_assignments.asset_id` / `person_id` | License gán cho máy hoặc cho người; phải có ít nhất một |
| `card_loans.person_id` | Người mượn là người bên ngoài; khi đó bắt buộc có `external_name` |
| `persons.department_id` | Chưa phân phòng ban |
| `persons.user_login_id` | Người sắp vào làm, chưa cấp tài khoản |
| `phones.location_id` | Thiết bị chưa gắn vị trí |
| `licenses.contract_id` | Gói license không gắn hợp đồng nào trong hệ thống |

## Từ điển dữ liệu

Mỗi bảng thay thế một phần của các file Excel hiện tại. Bảng dưới cho biết bảng dùng để làm gì và dữ liệu cũ nằm ở đâu, để khi nhập tay biết lấy từ file nào.

| Bảng | Dùng để làm gì | Nguồn Excel hiện tại |
| --- | --- | --- |
| `users` | 5 tài khoản đăng nhập hệ thống | Không có; IT tạo mới |
| `roles`, `role_permissions`, `user_permission_overrides` | Phân quyền | Không có; seed từ bảng RBAC ở trên |
| `departments` | Phòng ban, song ngữ EN/JA | Cột Department, sheet "2026" |
| `asset_categories` | Loại thiết bị | Cột PC, Monitor, sheet "2026" |
| `asset_tags` | Nhãn máy: Zscaler, MES | **Màu dòng** trong sheet "2026" |
| `locations` | Danh mục vị trí building/floor/room | File Phone List; cột セット関連, file 返却管理 |
| `persons` | Nhân viên. Bảng trung tâm | Cột PC Username, Staff code, Username, Email name, sheet "2026" |
| `person_secrets` | Mật khẩu PC/email dạng mã hóa | Cột password pc, password email, sheet "2026" |
| `assets` | Từng thiết bị vật lý | Cột PC Name, GA, S/N, Model, sheet "2026"; sheet "PC_Serial Number" |
| `asset_tag_links` | Thiết bị nào mang nhãn nào | Suy từ màu dòng |
| `assignments` | Lịch sử mượn–trả thiết bị | Cột Delivery status, Remarks, sheet "2026" |
| `license_products` | Danh mục phần mềm | Tiêu đề 6 cột license, sheet "2026" |
| `licenses` | Gói license đã mua | Sheet "Trendmicro"; hợp đồng IJCAD/PDF/Office |
| `license_assignments` | Lịch sử gán license cho máy/người | Giá trị trong 6 cột license, sheet "2026"; sheet "Trendmicro" |
| `access_cards` | Thẻ từ vật lý | File 返却管理 |
| `access_card_locations` | Thẻ nào vào được phòng nào | Cột セット関連, file 返却管理 |
| `card_loans` | Lịch sử mượn thẻ | Cột 備考, 貸出日, 返却日, file 返却管理 |
| `contracts` | Hợp đồng mua từ KDDI | Cột Sales Contract No. |
| `contract_lines` | Dòng hàng trong hợp đồng | Cột Spec, Total Qty, sheet "PC_Qty summary" |
| `phones` | Danh bạ máy nhánh | File Phone List |
| `audit_logs` | Nhật ký hệ thống tự ghi | Không có trong Excel |

### Các cột chung

Mọi bảng nghiệp vụ, trừ `audit_logs`, `role_permissions`, `user_permission_overrides`, `asset_tag_links` và `access_card_locations` (các bảng nối), có thêm 8 cột sau. Hệ thống tự điền, người dùng không nhập.

| Cột | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `created_at` | timestamptz | Thời điểm tạo bản ghi |
| `created_by` | FK → `users.id` | Người tạo |
| `updated_at` | timestamptz | Lần sửa gần nhất |
| `updated_by` | FK → `users.id` | Người sửa gần nhất |
| `is_deleted` | boolean | Đã xóa mềm hay chưa; mặc định false |
| `deleted_at` | timestamptz | Thời điểm xóa mềm |
| `deleted_by` | FK → `users.id` | Người xóa |
| `delete_reason` | varchar(300) | Lý do xóa, bắt buộc khi xóa |

### Các tập giá trị cố định (ENUM)

| Tập | Giá trị |
| --- | --- |
| `person_status` | SCHEDULED (sắp vào làm), ACTIVE (đang làm), RESIGNED (đã nghỉ) |
| `asset_status` | IN_STOCK (trong kho), IN_USE (đang mượn), REPAIR (đang sửa), DISPOSED (thanh lý), LOST (mất) |
| `card_status` | IN_STOCK, BORROWED, LOST, DAMAGED |
| `card_type` | STAFF, CONTRACTOR, GUEST |
| `delivery_status` | PENDING (chưa giao đủ), DELIVERED (đã giao đủ) |
| `license_type` | PERPETUAL, SUBSCRIPTION |
| `phone_device_type` | IP_PHONE, DECT_STATION, PBX, WIFI_PHONE |
| `audit_action` | CREATE, UPDATE, DELETE, RESTORE, LOGIN, LOGIN_FAIL, REVEAL |
| `permission_action` | view, add, change, delete |

> **Quy tắc đồng bộ trạng thái.** `assets.status` và `access_cards.status` là bản sao có chủ đích của thông tin suy ra được từ `assignments` / `card_loans`, giữ lại để lọc danh sách nhanh. Chúng **chỉ được cập nhật bởi service layer** trong cùng transaction với thao tác mượn/trả, không bao giờ sửa tay. Khi mượn: `IN_STOCK → IN_USE`. Khi trả: `IN_USE → IN_STOCK`. Các trạng thái REPAIR/DISPOSED/LOST/DAMAGED do người dùng đặt và chặn không cho mượn. Có một job đối chiếu chạy khi mở trang tổng quan để phát hiện lệch.

## Kiến trúc, tech stack và hạ tầng

Backend chuyển sang FastAPI. Giao diện vẫn render phía server để tránh phải bảo trì thêm một codebase frontend riêng.

| Lớp | Lựa chọn | Lý do |
| --- | --- | --- |
| Backend | FastAPI + Pydantic v2 | Đã chốt; async, docs tự sinh, type hint rõ |
| ORM & migration | SQLAlchemy 2.x + Alembic | Migration có phiên bản, bắt buộc với dữ liệu thật |
| Giao diện | Jinja2 server-side + HTMX cho tương tác nhỏ | Không cần build pipeline, không cần Node, một người bảo trì được |
| Màn hình nhập liệu | **SQLAdmin** (admin UI cho SQLAlchemy/FastAPI) | Thay thế gần nhất cho Django admin đã mất; dựng CRUD cho 23 bảng gần như tự động |
| Xác thực | Session cookie + Argon2id (`passlib`/`argon2-cffi`) | Đơn giản hơn JWT cho app nội bộ render server |
| Phân quyền | Tự xây: 4 bảng + FastAPI dependency `require(module, action)` | FastAPI không có sẵn; xem mục RBAC |
| Mã hóa dữ liệu nhạy cảm | `cryptography` – AES-256-GCM, khóa từ OS keyring | Nhà cung cấp DB cloud không bao giờ thấy khóa |
| Cơ sở dữ liệu | PostgreSQL 15+ | Partial unique index cho xóa mềm, ENUM, JSONB cho audit log |
| Audit log | Tự ghi qua SQLAlchemy event listener (`after_insert`, `after_update`) | Không có thư viện tương đương `django-auditlog` cho SQLAlchemy đủ chín |
| Đa ngôn ngữ | Babel + Jinja2 `gettext` | Tương đương Django i18n |
| Quản lý mã nguồn | Git, repo riêng tư | Lịch sử thay đổi, phục hồi khi máy hỏng |

**Cảnh báo về khối lượng công việc.** Django cung cấp sẵn auth, admin UI, RBAC và i18n — khoảng bốn hạng mục giờ phải tự làm. Ước lượng thận trọng là đợt 1 tốn **gấp 2–3 lần công sức** so với bản kế hoạch Django, phần lớn nằm ở màn hình nhập liệu cho 23 bảng và ở lớp kiểm tra quyền. SQLAdmin bù lại được phần lớn khoản nhập liệu nếu chấp nhận giao diện mặc định của nó. Nếu tiến độ căng, thứ tự cắt giảm nên là: FR-18 (xuất CSV) → FR-17 (trang tổng quan) → giao diện tự viết (dùng tạm SQLAdmin cho mọi màn hình).

**Hạ tầng đã chốt:** app FastAPI chạy trên laptop của IT (uvicorn), cơ sở dữ liệu dùng dịch vụ PostgreSQL online (Neon hoặc Supabase). Khi cần, app được chuyển lên máy chủ công ty.

Hệ quả cần biết:

- Trưởng GA và giám đốc chỉ vào được app khi laptop IT đang bật và cùng mạng LAN công ty (truy cập qua địa chỉ IP của laptop). Laptop tắt, mang ra ngoài hoặc hỏng thì không ai dùng được.
- Khi GA hoặc giám đốc bắt đầu dùng thường xuyên là thời điểm nên chuyển lên máy chủ công ty.
- Gói PostgreSQL free thường giới hạn dung lượng và có thể tạm dừng khi không dùng. Cần bật SSL, giới hạn IP truy cập nếu dịch vụ hỗ trợ, và chạy `pg_dump` định kỳ về máy công ty.
- Đóng gói bằng Docker Compose (app + Postgres local) để việc chuyển lên máy chủ chỉ là `docker compose up` và trỏ vào cùng cơ sở dữ liệu.

**Môi trường:** dev và production cùng nằm trên laptop IT nhưng tách hai cơ sở dữ liệu: PostgreSQL local để phát triển, PostgreSQL online cho dữ liệu thật, mỗi bên một file cấu hình. Khóa mã hóa của môi trường dev khác khóa production. Không thử code mới trên dữ liệu thật.

## Kế hoạch chuyển đổi dữ liệu từ Excel

IT nhập tay toàn bộ dữ liệu, theo thứ tự từ danh mục gốc đến giao dịch, vì bảng sau phụ thuộc bảng trước. Excel chỉ ngừng dùng khi đối chiếu số lượng khớp 100%.

1. **Đóng băng Excel:** chốt một ngày, chuyển các file sang chỉ đọc. Mọi thay đổi phát sinh sau ngày đó ghi thẳng vào app.

2. **Làm sạch trước khi nhập.** Quy tắc chung:
   - Ngày tháng nhập theo định dạng chuẩn của app, không gõ số serial Excel (46022).
   - Trạng thái chọn từ danh sách cố định thay vì chữ tự do ("Delivered to Mr. Chuong" → trạng thái IN_USE + người mượn).
   - **Màu ô Excel chuyển thành nhãn tường minh:** mỗi màu dòng trong sheet "2026" phải được dịch ra một `asset_tag` (Zscaler / MES). Làm bảng đối chiếu màu → nhãn trước khi nhập.
   - **Sửa lỗi chính tả tên phòng khi lập danh mục `locations`:** `Offce Room` → `Office Room` (5 dòng), `Analysys Room` → `Analysis Room`, `Sound side of process buiding` → `South side of process building`, `Offce RoomCabinet` → `Office Room Cabinet`. Đây là việc làm một lần, sau đó không ai gõ tay tên phòng nữa.
   - **Quy đổi quyền ra vào dạng câu sang danh sách phòng:** `倉庫のみ入退室許可` → chọn phòng Warehouse. `Document Room, Server Room, Master Room 以外の部屋` → chọn **tất cả** phòng có `is_access_controlled = true` **trừ** ba phòng đó. Phải liệt kê ra cụ thể, không lưu lại câu.
   - **Extension `N/A` nhập thành ô trống**, không nhập chuỗi "N/A".
   - **Mật khẩu:** nhập vào `person_secrets` qua màn hình chuyên dụng (có mã hóa), không copy paste hàng loạt. Đồng thời **đổi mật khẩu ngay** vì chúng đã nằm trong file dùng chung.

3. **Nhập theo thứ tự:**
   `roles` + `role_permissions` + `users` → `departments` → `locations` → `asset_categories` → `asset_tags` → `persons` → `person_secrets` → `contracts` + `contract_lines` → `assets` (serial, HWID, 2 MAC, mã GA, mã vendor) → `asset_tag_links` → `assignments` (thiết bị đang cho mượn) → `license_products` → `licenses` → `license_assignments` → `access_cards` + `access_card_locations` → `card_loans` (thẻ đang mượn) → `phones`

4. **Đối chiếu.** So số lượng trên app với Excel cho từng nhóm và ghi vào biên bản:
   - Tổng PC/màn hình theo từng hợp đồng KHCM khớp sheet "PC_Qty summary"
   - 13 license Trend Micro, 5 đang dùng
   - Số thẻ đang cho mượn (chưa có ngày trả)
   - 52 thiết bị trong Phone List
   - Số nhân viên theo từng phòng ban
   - Số máy mang nhãn Zscaler và nhãn MES khớp số dòng có màu tương ứng

5. **Kiểm thử bảo mật trước khi nhận:** đăng nhập bằng tài khoản GA Manager và thử gọi thẳng URL của màn hình mật khẩu và màn hình quản lý người dùng — phải trả 403. Thử xem mật khẩu bằng tài khoản Admin và kiểm tra có đúng một dòng REVEAL trong audit log.

6. **Xác nhận:** trưởng GA kiểm tra phần thẻ ra vào; một giám đốc xem thử trang tổng quan và duyệt file dịch tiếng Nhật.

7. **Cut-over:** ngừng dùng Excel, **xóa các cột mật khẩu khỏi bản lưu trữ**, lưu bản cuối ở thư mục chỉ đọc, thông báo cho người dùng.

Nhập liệu qua SQLAdmin là cách nhanh nhất cho một người. Nếu số bản ghi lớn hơn dự kiến, có thể bổ sung import CSV sau mà không ảnh hưởng thiết kế.

## Lộ trình triển khai

| Giai đoạn | Nội dung | Cổng kiểm soát |
| --- | --- | --- |
| 1. Đặc tả | BRD này được duyệt | **G1:** ban giám đốc duyệt BRD và duyệt việc đặt dữ liệu nhân viên trên cloud |
| 2. Nền tảng | Alembic migration 23 bảng, ENUM, partial unique index, CHECK; auth + RBAC + audit log; SQLAdmin | **G2:** chạy được bộ test ràng buộc — thử tạo 2 assignment cùng máy phải bị DB chặn |
| 3. Module lõi | Nhân sự (kèm mật khẩu), Tài sản, Mượn–trả, License | — |
| 4. Module còn lại | Thẻ ra vào, Hợp đồng, Phone List, tìm kiếm toàn cục, i18n | — |
| 5. Nhập liệu & đối chiếu | Theo kế hoạch chuyển đổi ở trên | **G3:** biên bản đối chiếu khớp 100% + GA và một giám đốc xác nhận |
| 6. Cut-over & vận hành | Ngừng Excel, backup định kỳ, README | — |

Thời lượng từng giai đoạn chưa được ước lượng; IT điền mốc ngày sau khi BRD được duyệt.

## Rủi ro và quyết định đã chốt

| Rủi ro | Mức | Giảm thiểu |
| --- | --- | --- |
| **Lưu mật khẩu nhân viên trong hệ thống**: một lỗ hổng phân quyền hoặc một lần lộ khóa là lộ toàn bộ | **Cao** | Bảng riêng; mã hóa phía ứng dụng; khóa ngoài Git và ngoài backup; quyền `secrets.view` chỉ Admin; bắt xác minh lại mật khẩu đăng nhập; token sống 2 phút; audit mọi lần xem; khóa sau 5 lần sai; chỉ một endpoint trả giá trị thật; kiểm thử 403 trước go-live |
| **Khóa mã hóa nằm trên laptop IT**: mất laptop là mất cả DB string lẫn khóa | **Cao** | BitLocker; khóa cất trong Windows Credential Manager chứ không trong file; bản sao in giấy trong két giám đốc; mất máy thì đổi mật khẩu DB **và** xoay khóa **và** đổi toàn bộ mật khẩu nhân viên |
| **Tự xây RBAC trên FastAPI**: dễ sót một endpoint không kiểm quyền | **Cao** | Mặc định từ chối — dependency kiểm quyền gắn ở cấp router, endpoint phải khai báo rõ mới mở; danh sách endpoint rà một lần trước go-live; test tự động cho mỗi vai trò |
| **Mất Django admin**: 23 bảng phải tự dựng màn hình | **Cao** | Dùng SQLAdmin cho toàn bộ CRUD; chỉ tự viết màn hình cho tổng quan, hồ sơ một người và luồng xem mật khẩu |
| Chỉ một người IT: nghỉ phép dài hoặc nghỉ việc thì không ai vận hành được | Cao | README, hướng dẫn backup/khôi phục/xoay khóa, code trên Git, `pg_dump` mới nhất, khóa mã hóa cất ở két |
| App chạy trên laptop IT: laptop tắt hoặc rời văn phòng thì người khác không truy cập được | Cao | Chuyển lên máy chủ công ty khi GA/giám đốc bắt đầu dùng thường xuyên |
| Mật khẩu đang nằm trong Excel dùng chung | Cao | Coi như đã lộ: đổi ngay khi nhập sang app, xóa cột khỏi file lưu trữ |
| Gói PostgreSQL free: tạm dừng, giới hạn dung lượng, không SLA, dữ liệu ở nước ngoài | Trung bình | Backup hằng ngày về máy công ty; **xin xác nhận bằng văn bản của ban giám đốc** trước khi đặt dữ liệu nhân viên và mật khẩu trên cloud nước ngoài |
| Nhập tay sai hoặc thiếu | Trung bình | Làm sạch trước, đối chiếu số lượng theo 6 nhóm, GA xác nhận phần thẻ |
| Phình phạm vi | Trung bình | Mọi yêu cầu mới ghi vào danh sách đợt sau, không chen vào đợt 1 |
| Quy đổi "trừ các phòng X, Y, Z" sai sót | Trung bình | Làm bảng đối chiếu trước, GA duyệt danh sách phòng của từng thẻ |
| Bản dịch tiếng Nhật chưa tự nhiên | Thấp | Nhờ một giám đốc người Nhật duyệt file dịch trước UAT |

### Nhật ký quyết định

| Ngày | Quyết định |
| --- | --- |
| 2026-10-05 | IT là người phát triển, bảo trì và nhập liệu duy nhất |
| 2026-10-05 | Xóa mềm cho mọi bản ghi nghiệp vụ |
| 2026-10-05 | Chuyển đổi dữ liệu bằng nhập tay; ngừng Excel khi nhập xong |
| 2026-10-05 | Chưa xây hệ thống cảnh báo và giao diện điện thoại |
| 2026-10-05 | Hạ tầng: app chạy trên laptop IT + PostgreSQL online; chuyển lên máy chủ công ty khi cần |
| 2026-10-05 | Không quản lý nhà thầu; thẻ cho người bên ngoài mượn ghi tên, công ty bằng chữ |
| 2026-10-05 | Hợp đồng chỉ lưu mã, thiết bị, số lượng, tình trạng nhận và giao |
| 2026-10-05 | Dev và production tách hai cơ sở dữ liệu trên cùng laptop |
| **2026-10-06** | **Backend đổi từ Django sang FastAPI; RBAC, admin UI, i18n tự xây** |
| **2026-10-06** | **Lưu mật khẩu PC/email, mã hóa AES-256-GCM phía ứng dụng, bảng riêng, hiển thị che, xem phải xác minh lại mật khẩu đăng nhập, ghi audit mỗi lần xem** |
| **2026-10-06** | **Phone List vào đợt 1, làm sau cùng; dùng chung bảng `locations` với module Thẻ ra vào** |
| **2026-10-06** | **Nhãn thiết bị (Zscaler, MES) lưu bằng bảng `asset_tags` + bảng nối, không dùng cột boolean** |
| **2026-10-06** | **Tài sản có hai mã song song: `asset_code` (tem GA) và `vendor_code` (mã KDDI); hai cột MAC riêng cho LAN và Wi-Fi** |
| **2026-10-06** | **Quyền ra vào của thẻ lưu bằng bảng nối thẻ–phòng, không lưu câu mô tả; "trừ phòng X" quy đổi thành danh sách phòng khi nhập** |
| **2026-10-06** | **`contract_lines` không có `delivered_qty`; số đã nhận đếm từ `assets`** |
| **2026-10-06** | **`license_assignments` có `expiry_date` riêng để xử lý hạn theo từng máy của Trend Micro** |
| **2026-10-06** | **Tài sản có 5 trạng thái: Trong kho, Đang mượn, Đang sửa, Thanh lý, Mất** |
| **2026-10-06** | **Mọi trạng thái dùng ENUM của PostgreSQL; mọi ràng buộc toàn vẹn đặt ở tầng DB, không chỉ ở code** |

---

## Phụ lục: những điểm đã sửa so với bản thiết kế do Gemini đề xuất

Ghi lại để không lặp lại khi tham chiếu tài liệu cũ.

| # | Vấn đề ở bản Gemini | Xử lý trong BRD này |
| --- | --- | --- |
| 1 | `UNIQUE (device_id, returned_date)` không chặn được hai lần cho mượn cùng máy vì `NULL ≠ NULL` | Partial unique index `WHERE returned_at IS NULL` |
| 2 | `UNIQUE (license_id, device_id)` chặn việc gán lại license sau khi thu hồi | Partial unique index `WHERE removed_at IS NULL` |
| 3 | `license_assignments` không có `removed_at`, chỉ có `status` | Thêm `removed_at`; `status` bỏ đi vì suy ra được |
| 4 | Thiếu CHECK "license phải gán cho máy hoặc người" | Đã thêm |
| 5 | Trạng thái là `VARCHAR` tự do | Dùng ENUM của PostgreSQL |
| 6 | `access_card_permissions.permission_scope` là chuỗi tự do — đúng lỗi mà chính tài liệu đó phê phán | Bảng nối `access_card_locations` |
| 7 | `has_zscaler`, `is_mes_machine` là cột boolean cứng | Bảng `asset_tags` + `asset_tag_links` |
| 8 | `delivered_qty` nhập tay, `remaining_qty` tính từ nó — chép nguyên painpoint của Excel | Bỏ cả hai; đếm từ `assets` |
| 9 | Không có audit log, xóa mềm chỉ có ở 2/15 bảng | `audit_logs` chỉ-thêm; 8 cột chung trên mọi bảng nghiệp vụ |
| 10 | Không có bảng người dùng / vai trò / quyền | 4 bảng RBAC |
| 11 | `card_borrow_logs` không nối với nhân viên; `contractor_type` bắt buộc còn tên người mượn thì không | `person_id` nullable + `external_name`/`external_company` + CHECK |
| 12 | `employees.user_id NOT NULL` trong khi người sắp vào làm chưa có user ID | `user_login_id` nullable |
| 13 | Không có cột song ngữ ở bảng danh mục | `name_en` / `name_ja` ở mọi danh mục |
| 14 | `pgcrypto` với khóa truyền qua SQL tới DB cloud bên thứ ba | Mã hóa phía ứng dụng, khóa không rời laptop |
| 15 | Mật khẩu nằm chung bảng với hồ sơ nhân viên | Bảng `person_secrets` riêng |
| 16 | Thiếu ràng buộc ngày (trả ≥ mượn, hết hạn ≥ bắt đầu) | Đã thêm CHECK |
| 17 | Không xử lý `expire date` theo từng PC của Trend Micro | `license_assignments.expiry_date` |
| 18 | Không có cơ chế chặn gán vượt số seat | FR-12 kiểm tra ở service layer khi gán |
