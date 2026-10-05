# Hệ thống Quản lý Tài sản IT – Tokuyama Vietnam: Tài liệu Yêu cầu & Kế hoạch (BRD)

Oct 5, 2026 · @AJ Pham

## Tóm tắt dự án

Dự án xây một web app nội bộ bằng Django + PostgreSQL, thay thế toàn bộ các file Excel quản lý thiết bị, license, thẻ ra vào và tình trạng giao hàng theo mã hợp đồng. Mục tiêu là một nguồn dữ liệu duy nhất cho IT và GA. Tài liệu đang ở giai đoạn lập kế hoạch (vai trò BA / Solution Architect).

| Hạng mục | Nội dung |
| --- | --- |
| Tên dự án | Hệ thống Quản lý Tài sản IT (IT Asset Management – ITAM) |
| Đơn vị | Tokuyama Vietnam (TVC) |
| Chủ dự án, developer, người bảo trì | IT (người duy nhất của bộ phận IT) |
| Người dùng | 1 IT, 1 trưởng GA, 3 giám đốc người Nhật (tổng 5) |
| Công nghệ | Django + PostgreSQL |
| Chuyển đổi dữ liệu | Nhập tay toàn bộ bởi IT, sau đó ngừng dùng Excel |
| Ngoài phạm vi đợt này | Hệ thống cảnh báo tự động, giao diện điện thoại |
| Giai đoạn hiện tại | Khảo sát và đặc tả yêu cầu |

## Hiện trạng và painpoint

Thông tin tài sản IT đang nằm rải rác ở nhiều file và sheet Excel không liên kết. Hậu quả là dữ liệu trùng lặp, lệch nhau, không ai biết hạn và lộ thông tin nhạy cảm. Bảng dưới là bằng chứng lấy từ chính các file hiện tại.

| Nguồn hiện tại | Đang quản lý | Vấn đề quan sát được |
| --- | --- | --- |
| Sheet "2026" | Nhân viên, tên PC, tài khoản, license, trạng thái giao, S/N | Lưu mật khẩu PC và email dạng chữ thường; trạng thái là chữ tự do, có lỗi chính tả; màu cam/nâu mang nghĩa ngầm không được ghi lại; ngày hiện dạng số serial (46022) |
| Sheet "PC\_Serial Number" | Serial PC và màn hình theo số báo giá KHCM | Trùng với cột S/N của sheet "2026", phải sửa tay hai nơi |
| Sheet "PC\_Qty summary" | Số lượng mua, đã giao, đang cài đặt, còn lại | Nhập tay, ghi "update by Aug 11th" nên có thể đã cũ |
| Sheet "Trendmicro" | 13 license, 5 đang dùng | 3/5 license đang dùng không có ngày hết hạn |
| File 返却管理 (thẻ ra vào) | Thẻ cho nhà thầu mượn, quyền vào phòng | Thẻ mượn từ tháng 6–7/2026 vẫn trống ngày trả; định dạng ngày lẫn lộn (29/09/2026 và 29/9/2026) |
| File hợp đồng KDDI, license IJCAD/PDF/Office | Hợp đồng, license | Không liên kết với thiết bị hay người dùng |

Painpoint chính:

1. **Phân mảnh:** muốn biết "nhân viên A đang giữ gì" phải mở nhiều file.
2. **Trùng lặp và lệch dữ liệu:** cùng một serial được nhập ở nhiều nơi.
3. **Không có lịch sử:** không biết thiết bị đã qua tay những ai.
4. **Dễ quên:** không thấy license sắp hết hạn hay thẻ chưa trả.
5. **Rủi ro bảo mật:** mật khẩu nằm trong file dùng chung.

## Mục tiêu và chỉ số thành công

Dự án thành công khi toàn bộ file Excel liên quan được ngừng dùng và mọi tra cứu tài sản đều làm được trên app.

| Mục tiêu | Chỉ số đo | Ngưỡng đạt |
| --- | --- | --- |
| Một nguồn dữ liệu duy nhất | Số file Excel quản lý tài sản còn được cập nhật | 0 sau ngày cut-over |
| Tra cứu nhanh | Thời gian trả lời "thiết bị X đang ở đâu, ai giữ" | Dưới 30 giây |
| Không mất dấu | Thiết bị, license, thẻ có lịch sử đầy đủ người giữ | 100% bản ghi tạo sau go-live |
| Không quên hạn | License có ngày hết hạn hoặc ghi rõ vĩnh viễn | 100% |
| Bảo mật | Mật khẩu người dùng lưu trong hệ thống | 0 (không lưu) |

## Phạm vi và người dùng

Đợt 1 gồm 6 module nghiệp vụ, dùng trên trình duyệt máy tính. Cảnh báo tự động và giao diện điện thoại để dành cho các đợt sau. Người dùng hệ thống chỉ có 5 người, còn toàn bộ nhân viên là đối tượng dữ liệu, không đăng nhập.

| Module | Nội dung | Đợt |
| --- | --- | --- |
| Nhân sự | Danh mục nhân viên (mã TVC, phòng ban, trạng thái làm việc) | 1 |
| Tài sản | Laptop, màn hình, điện thoại, chuột, phụ kiện: mã PC, model, serial, HWID, MAC, trạng thái | 1 |
| Mượn – trả thiết bị | Cho nhân viên mượn thiết bị, nhận trả, lịch sử đầy đủ | 1 |
| License | IJCAD, Office LTSC, PDF, Trend Micro, MS365, Visio, Windows: số lượng, gán cho máy/người, ngày hết hạn | 1 |
| Thẻ ra vào | Thẻ, phòng được phép vào, ai mượn, ngày mượn/trả | 1 |
| Hợp đồng | Chỉ lưu mã hợp đồng (KHCM-…), thiết bị và số lượng, đã nhận đủ hay chưa, đã giao hay chưa | 1 |
| Cảnh báo email/Teams | Tự nhắc license hết hạn, thẻ quá hạn | Sau |
| Giao diện điện thoại, quét QR | Kiểm kê bằng điện thoại | Sau |

**Ngoài phạm vi:** quản lý nhân sự nhà thầu, lưu nội dung hợp đồng (giá, điều khoản, file), lưu mật khẩu PC/email, tự động quét thiết bị qua Intune/AD, quy trình phê duyệt mua sắm, cổng để nhân viên tự gửi yêu cầu.

| Người dùng | Vai trò trong hệ thống | Mục đích chính |
| --- | --- | --- |
| IT | Admin | Nhập liệu, quản lý tài sản/license, quản lý người dùng và quyền |
| Trưởng GA | GA Manager | Quản lý thẻ ra vào, tra cứu tài sản |
| 3 giám đốc người Nhật | Executive | Xem tổng quan, tra cứu, xem hợp đồng |

## Phân quyền RBAC và bảo mật

IT là Admin có toàn quyền và là người duy nhất tạo người dùng, gán vai trò. Mọi người dùng khác được giới hạn theo 4 quyền Đọc / Ghi (thêm) / Sửa / Xóa trên từng module. Bốn quyền này khớp đúng với cơ chế có sẵn của Django (view / add / change / delete gắn vào Group), nên không cần tự xây khung phân quyền.

Ký hiệu: Đ = đọc, G = ghi (thêm mới), S = sửa, X = xóa (xóa mềm).

| Module | Admin (IT) | GA Manager | Executive |
| --- | --- | --- | --- |
| Nhân sự | Đ G S X | Đ G S | Đ |
| Tài sản | Đ G S X | Đ | Đ |
| Mượn – trả thiết bị | Đ G S X | Đ | Đ |
| License (key bị che) | Đ G S X | — | Đ |
| Thẻ ra vào | Đ G S X | Đ G S X | Đ |
| Hợp đồng | Đ G S X | Đ | Đ |
| Nhật ký thay đổi (audit log) | Đ | — | Đ |
| Thùng rác (khôi phục bản ghi đã xóa) | Đ S | — | — |
| Quản lý người dùng & vai trò | Đ G S X | — | — |

Bảng trên là cấu hình mặc định. Admin có thể chỉnh quyền từng vai trò hoặc từng người dùng mà không cần sửa code.

**Quy tắc bảo mật:**

- **Đăng nhập:** đợt 1 dùng tài khoản Django có sẵn với mật khẩu mạnh. SSO bằng Microsoft Entra ID (kèm MFA) làm khi chuyển lên máy chủ công ty, vì Entra ID cần HTTPS và tên miền cố định.
- **Khi IT vắng mặt:** README và bản pg\_dump mới nhất đủ để người khác dựng lại app trên một máy khác.
- **Không lưu mật khẩu** PC hay email của nhân viên. Các cột mật khẩu trong Excel cũ không được nhập sang và cần được xóa khỏi file cũ.
- **Che dữ liệu nhạy cảm:** license key chỉ Admin thấy đầy đủ.
- **Audit log:** mọi thao tác thêm/sửa/xóa/khôi phục đều ghi ai, lúc nào, bản ghi nào, giá trị trước và sau. Không ai sửa được audit log, kể cả Admin.
- **Phiên làm việc:** tự đăng xuất sau 30 phút không thao tác. Đợt 1 truy cập qua HTTP trong LAN; bật HTTPS khi lên máy chủ công ty.

## Yêu cầu chức năng

Đợt 1 có 13 yêu cầu (12 Must, 1 Should). Ưu tiên theo MoSCoW.

| Mã | Yêu cầu | Module | Ưu tiên |
| --- | --- | --- | --- |
| FR-01 | Đăng nhập, đăng xuất, phân quyền theo vai trò | Hệ thống | Must |
| FR-02 | Admin tạo người dùng, gán vai trò, chỉnh quyền Đ/G/S/X | Hệ thống | Must |
| FR-03 | Tìm kiếm toàn cục theo mã PC, serial, HWID, MAC, tên người, mã hợp đồng | Hệ thống | Must |
| FR-04 | Thêm/sửa/xóa mềm nhân viên; đánh dấu đã nghỉ việc | Nhân sự | Must |
| FR-05 | Thêm/sửa/xóa mềm tài sản; lưu serial, HWID, địa chỉ MAC | Tài sản | Must |
| FR-06 | Trạng thái tài sản: Trong kho, Đang mượn, Mất | Tài sản | Must |
| FR-07 | Cho mượn và nhận trả thiết bị, lưu lịch sử người mượn | Mượn – trả | Must |
| FR-08 | Hồ sơ một người: mọi thiết bị, license, thẻ đang giữ và đã từng giữ | Nhân sự | Must |
| FR-09 | Quản lý license: tổng số, đã gán, còn trống, ngày hết hạn; gán cho máy hoặc người | License | Must |
| FR-10 | Cho mượn/trả thẻ ra vào, ghi phòng được phép, mục đích, ngày mượn/trả; người mượn là nhân viên hoặc người bên ngoài (ghi tên, công ty) | Thẻ | Must |
| FR-11 | Mã hợp đồng (vd KHCM-2408-0113): thiết bị và số lượng đặt; số đã nhận tự tính từ tài sản gắn vào hợp đồng; hiển thị đã nhận đủ hay chưa và đã giao hay chưa | Hợp đồng | Must |
| FR-12 | Chuyển ngôn ngữ Anh/Nhật, lưu theo từng người; sáng/tối tự theo hệ điều hành | Hệ thống | Must |
| FR-13 | Trang tổng quan: số thiết bị theo trạng thái, license sắp hết hạn (60 ngày), thẻ đang cho mượn | Tổng quan | Should |

FR-11 thay thế sheet "PC\_Qty summary": số đã giao không còn gõ tay mà được đếm từ tài sản thực tế. FR-13 chỉ hiển thị khi mở trang, không gửi thông báo, nên không mâu thuẫn với quyết định chưa làm cảnh báo.

## Yêu cầu phi chức năng

Các yêu cầu dưới đây phân nhóm theo mô hình chất lượng ISO/IEC 25010. Vì chỉ có một người phát triển và bảo trì, nhóm "Bảo trì" được coi là quan trọng ngang bảo mật.

| Mã | Nhóm | Yêu cầu |
| --- | --- | --- |
| NFR-01 | Đa ngôn ngữ | Giao diện tiếng Anh và tiếng Nhật bằng Django i18n; cấu trúc sẵn để thêm tiếng Việt chỉ bằng file dịch. Dữ liệu nhập tay (tên, ghi chú) không được dịch. |
| NFR-02 | Giao diện | Trang admin Django có sẵn nút đổi sáng/tối. Trang tự viết: tự theo hệ điều hành nhờ thẻ meta color-scheme, không cần CSS. |
| NFR-03 | Tương thích | Chrome và Edge bản mới trên máy tính, màn hình từ 1366px |
| NFR-04 | Hiệu năng | Trang danh sách và tìm kiếm phản hồi dưới 2 giây với 10.000 bản ghi |
| NFR-05 | Bảo mật | Mật khẩu hệ thống băm bằng cơ chế mặc định của Django, chống CSRF/XSS, không lưu mật khẩu PC/email; HTTPS và SSO/MFA khi lên máy chủ công ty |
| NFR-06 | Truy vết | Xóa mềm cho mọi bản ghi nghiệp vụ; audit log không sửa được, giữ tối thiểu 5 năm |
| NFR-07 | Bảo trì | Code trên Git (repo riêng tư), có README cài đặt, hướng dẫn backup/khôi phục, mô tả mô hình dữ liệu |

## Nguyên tắc mô hình dữ liệu và xóa mềm

Dữ liệu xoay quanh ba thực thể gốc là Người, Tài sản và License. Mọi quan hệ "ai giữ cái gì" được lưu ở bảng giao dịch có ngày bắt đầu/kết thúc, nên lịch sử không bao giờ bị ghi đè. Chi tiết từng bảng và từng cột xem sơ đồ ERD và từ điển dữ liệu ngay dưới đây.

**Trường chung** trên mọi bảng nghiệp vụ: `created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`, `deleted_at`, `deleted_by`, `delete_reason`.

**Quy tắc xóa mềm:**

1. Mất hay nhân viên nghỉ việc là **trạng thái**, không phải xóa. Xóa mềm chỉ dành cho bản ghi nhập sai hoặc trùng.
2. Bấm "Xóa" chỉ đặt `is_deleted = true` và bắt buộc nhập lý do. Mọi màn hình và truy vấn mặc định ẩn bản ghi đã xóa.
3. Ràng buộc duy nhất (serial, mã tài sản, số thẻ) chỉ áp dụng cho bản ghi chưa xóa, dùng partial unique index của PostgreSQL.
4. Chỉ Admin xem được thùng rác và khôi phục bản ghi.
5. Không xóa được tài sản đang mượn hoặc license đang gán; phải thu hồi trước.
6. Bản ghi Assignment, LicenseAssignment, CardLoan, AuditLog không xóa được, chỉ đóng bằng ngày kết thúc.

## Sơ đồ cơ sở dữ liệu (ERD)

Cơ sở dữ liệu có 15 bảng; Person và Asset là hai bảng trung tâm, các bảng còn lại nối vào chúng.

&#91;embedded content: ERD · 15 bảng, 14 quan hệ\]

AccessCardRoom là bảng nối cho quan hệ nhiều-nhiều giữa thẻ và phòng.

Các khóa ngoại được phép để trống: contract\_line\_id của Asset (tài sản không thuộc hợp đồng nào), asset\_id hoặc person\_id của LicenseAssignment (license gán cho máy hoặc cho người, cần có ít nhất một), person\_id của CardLoan (khi người mượn là người bên ngoài thì ghi external\_name và external\_company).

Mọi bảng nghiệp vụ trừ AuditLog còn có các trường chung (created\_at, created\_by, updated\_at, updated\_by, is\_deleted, deleted\_at, deleted\_by, delete\_reason); các trường \_by trỏ tới bảng người dùng của Django. Ràng buộc duy nhất của serial, asset\_code, card\_no và code (Contract) chỉ áp dụng cho bản ghi chưa xóa.

## Từ điển dữ liệu

Mỗi bảng thay thế một phần của các file Excel hiện tại. Bảng dưới cho biết bảng dùng để làm gì và dữ liệu cũ nằm ở đâu, để khi nhập tay biết lấy từ file nào.

| Bảng | Dùng để làm gì | Nguồn Excel hiện tại |
| --- | --- | --- |
| Department | Phòng ban của công ty, có tên tiếng Anh và tiếng Nhật | Cột Department, sheet "2026" |
| Person | Nhân viên. Là bảng trung tâm: mọi thiết bị, license, thẻ đều gắn về một người | Cột PC Username, Staff code, sheet "2026" |
| AssetCategory | Loại thiết bị (laptop, màn hình, điện thoại, chuột…) | Cột PC, Monitor, sheet "2026" |
| Asset | Từng thiết bị cụ thể, mỗi dòng một thiết bị với serial riêng. Là bảng trung tâm thứ hai | Cột S/N, sheet "2026"; sheet "PC\_Serial Number" |
| Assignment | Lịch sử mượn–trả thiết bị. Mỗi dòng là một lần mượn của một người, nên tra được thiết bị đã qua tay ai | Cột Delivery status, Remarks, sheet "2026" |
| LicenseProduct | Danh mục phần mềm có license: IJCAD, Office LTSC, PDF, Trend Micro, MS365, Visio, Windows | Tiêu đề các cột license, sheet "2026" |
| License | Một gói license đã mua: số lượng được dùng, hạn sử dụng | Sheet "Trendmicro" (13 license) |
| LicenseAssignment | Lịch sử gán license cho một máy hoặc một người | Sheet "Trendmicro"; các cột license, sheet "2026" |
| Room | Phòng cần kiểm soát ra vào (Kho, Server Room, Document Room…) | Cột セット関連, file 返却管理 |
| AccessCard | Thẻ từ vật lý | File 返却管理 |
| AccessCardRoom | Bảng nối: thẻ nào được vào những phòng nào | Cột セット関連, file 返却管理 |
| CardLoan | Lịch sử mượn thẻ: ai mượn, mượn khi nào, đã trả chưa | Cột 備考, 貸出日, 返却日, file 返却管理 |
| Contract | Hợp đồng mua, chỉ lưu mã (KHCM-…) và tình trạng giao hàng | Cột Sales Contract No., sheet "PC\_Qty summary" |
| ContractLine | Từng dòng hàng trong hợp đồng: loại thiết bị, cấu hình, số lượng đặt | Sheet "PC\_Qty summary" |
| AuditLog | Nhật ký thay đổi dữ liệu do hệ thống tự ghi, không nhập tay | Không có trong Excel |

### Ý nghĩa các cột

Kiểu "Danh sách chọn" nghĩa là người dùng chọn từ giá trị cố định, không gõ tự do. "Duy nhất" chỉ tính trên bản ghi chưa xóa mềm.

| Bảng | Cột | Kiểu | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Department | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| Department | name\_en | Chữ | Có | Tên phòng ban bằng tiếng Anh |
| Department | name\_ja | Chữ | Không | Tên bằng tiếng Nhật, hiện khi giao diện tiếng Nhật; trống thì dùng name\_en |
| Person | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| Person | staff\_code | Chữ | Có | Mã nhân viên, ví dụ TVC00001. Duy nhất |
| Person | full\_name | Chữ | Có | Họ tên |
| Person | department\_id | Khóa ngoại → Department | Không | Phòng ban của nhân viên |
| Person | status | Danh sách chọn | Có | Đang làm hoặc Đã nghỉ việc. Nghỉ việc là trạng thái, không xóa bản ghi |
| AssetCategory | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| AssetCategory | name | Chữ | Có | Tên loại: laptop, màn hình, điện thoại, chuột… |
| Asset | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| Asset | asset\_code | Chữ | Có | Mã tài sản của công ty, ví dụ TKY-PC0001. Duy nhất |
| Asset | category\_id | Khóa ngoại → AssetCategory | Có | Thiết bị thuộc loại nào |
| Asset | contract\_line\_id | Khóa ngoại → ContractLine | Không | Dòng hợp đồng đã mua thiết bị này; trống nếu không thuộc hợp đồng nào |
| Asset | model | Chữ | Không | Model, ví dụ Dell Pro 16 (PC16250) |
| Asset | serial | Chữ | Không | Số serial in trên máy. Duy nhất |
| Asset | hwid | Chữ | Không | Mã phần cứng (hardware ID) của máy |
| Asset | mac\_address | Chữ | Không | Địa chỉ MAC của máy, chỉ là một cột thông tin |
| Asset | status | Danh sách chọn | Có | Trong kho, Đang mượn hoặc Mất |
| Asset | note | Chữ dài | Không | Ghi chú tự do, tương ứng cột Remarks trong Excel |
| Assignment | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| Assignment | asset\_id | Khóa ngoại → Asset | Có | Thiết bị được mượn |
| Assignment | person\_id | Khóa ngoại → Person | Có | Người mượn |
| Assignment | borrowed\_at | Ngày | Có | Ngày bắt đầu mượn |
| Assignment | returned\_at | Ngày | Không | Ngày trả; trống nghĩa là đang mượn |
| Assignment | note | Chữ dài | Không | Ghi chú, ví dụ "giao ngày 8/5, chưa cài mail" |
| LicenseProduct | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| LicenseProduct | name | Chữ | Có | Tên phần mềm: IJCAD, Office LTSC, PDF, Trend Micro… |
| License | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| License | product\_id | Khóa ngoại → LicenseProduct | Có | License của phần mềm nào |
| License | seats | Số nguyên | Có | Số máy hoặc người được dùng theo gói này |
| License | license\_key | Chữ | Không | Mã kích hoạt; chỉ Admin thấy đầy đủ |
| License | start\_date | Ngày | Không | Ngày bắt đầu hiệu lực |
| License | expiry\_date | Ngày | Không | Ngày hết hạn; trống nghĩa là vĩnh viễn |
| LicenseAssignment | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| LicenseAssignment | license\_id | Khóa ngoại → License | Có | Gói license đang được gán |
| LicenseAssignment | asset\_id | Khóa ngoại → Asset | Không | Gán cho máy nào |
| LicenseAssignment | person\_id | Khóa ngoại → Person | Không | Gán cho người nào. Phải có asset\_id hoặc person\_id |
| LicenseAssignment | assigned\_at | Ngày | Có | Ngày gán |
| LicenseAssignment | removed\_at | Ngày | Không | Ngày gỡ; trống nghĩa là đang dùng |
| Room | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| Room | name | Chữ | Có | Tên phòng |
| AccessCard | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| AccessCard | card\_no | Chữ | Có | Số thẻ in trên thẻ. Duy nhất |
| AccessCardRoom | card\_id | Khóa ngoại → AccessCard | Có | Thẻ nào |
| AccessCardRoom | room\_id | Khóa ngoại → Room | Có | Được vào phòng nào. Mỗi cặp thẻ–phòng chỉ xuất hiện một lần |
| CardLoan | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| CardLoan | card\_id | Khóa ngoại → AccessCard | Có | Thẻ được mượn |
| CardLoan | person\_id | Khóa ngoại → Person | Không | Nhân viên mượn thẻ; trống nếu người mượn là người bên ngoài |
| CardLoan | external\_name | Chữ | Không | Tên người bên ngoài mượn. Bắt buộc khi person\_id trống |
| CardLoan | external\_company | Chữ | Không | Công ty của người bên ngoài |
| CardLoan | purpose | Chữ | Không | Mục đích mượn, ví dụ nhân viên kho, nhân viên vệ sinh |
| CardLoan | borrowed\_at | Ngày | Có | Ngày mượn |
| CardLoan | returned\_at | Ngày | Không | Ngày trả; trống nghĩa là chưa trả |
| Contract | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| Contract | code | Chữ | Có | Mã hợp đồng, ví dụ KHCM-2408-0113. Duy nhất |
| Contract | delivery\_status | Danh sách chọn | Có | Chưa giao hoặc Đã giao |
| ContractLine | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| ContractLine | contract\_id | Khóa ngoại → Contract | Có | Dòng hàng thuộc hợp đồng nào |
| ContractLine | item\_type | Chữ | Có | Loại hàng đặt: PC 16 inch, PC 14 inch, màn hình… |
| ContractLine | spec | Chữ | Không | Cấu hình, ví dụ Dell Pro 16 (PC16250) XCTO Base |
| ContractLine | qty\_ordered | Số nguyên | Có | Số lượng đặt. Số đã nhận được đếm từ Asset gắn vào dòng này, không nhập tay |
| AuditLog | id | Số nguyên (PK) | Có | Mã nội bộ tự tăng |
| AuditLog | user\_id | Khóa ngoại → người dùng Django | Có | Ai thực hiện thao tác |
| AuditLog | created\_at | Ngày giờ | Có | Thời điểm thao tác |
| AuditLog | table\_name | Chữ | Có | Bảng bị thay đổi |
| AuditLog | record\_id | Số nguyên | Có | Mã bản ghi bị thay đổi |
| AuditLog | action | Danh sách chọn | Có | Thêm, Sửa, Xóa hoặc Khôi phục |
| AuditLog | before\_after | JSON | Không | Giá trị trước và sau khi thay đổi |

### Các cột chung

Mọi bảng nghiệp vụ, trừ AuditLog, có thêm 8 cột sau. Hệ thống tự điền, người dùng không nhập.

| Cột | Kiểu | Ý nghĩa |
| --- | --- | --- |
| created\_at | Ngày giờ | Thời điểm tạo bản ghi |
| created\_by | Khóa ngoại → người dùng Django | Người tạo |
| updated\_at | Ngày giờ | Lần sửa gần nhất |
| updated\_by | Khóa ngoại → người dùng Django | Người sửa gần nhất |
| is\_deleted | Đúng/Sai | Đã xóa mềm hay chưa; mặc định Sai |
| deleted\_at | Ngày giờ | Thời điểm xóa mềm |
| deleted\_by | Khóa ngoại → người dùng Django | Người xóa |
| delete\_reason | Chữ | Lý do xóa, bắt buộc khi xóa |

## Kiến trúc, tech stack và hạ tầng

Đã chốt Django + PostgreSQL, render giao diện phía server (không tách frontend riêng). Đây là kiến trúc ít thành phần nhất, phù hợp với một người vừa phát triển vừa bảo trì.

| Lớp | Lựa chọn | Lý do |
| --- | --- | --- |
| Backend | Django (bản LTS) | Có sẵn auth, Group/Permission (khớp RBAC Đ/G/S/X), i18n, migration, trang admin để nhập liệu nhanh |
| Giao diện | Django templates: trang admin có sẵn của Django (đã có CSS, sáng/tối, tiếng Nhật) cho nhập liệu và quản lý; các trang tự viết (tổng quan, hồ sơ một người) dùng HTML thuần, chưa viết CSS | Ra bản dùng được nhanh nhất; CSS thêm sau không phải sửa logic |
| Cơ sở dữ liệu | PostgreSQL | Partial unique index cho xóa mềm, JSON cho audit log |
| Audit log | Thư viện có sẵn (ví dụ django-simple-history hoặc django-auditlog) | Không tự viết lại |
| Đăng nhập | Tài khoản Django có sẵn (đợt 1); OIDC với Microsoft Entra ID khi lên máy chủ | Entra ID cần HTTPS và tên miền cố định, chưa có khi chạy trên laptop |
| Quản lý mã nguồn | Git, repo riêng tư | Lịch sử thay đổi, phục hồi khi máy hỏng |

**Hạ tầng đã chốt:** app Django chạy trên laptop của IT, cơ sở dữ liệu dùng dịch vụ PostgreSQL online (ví dụ Neon, Supabase). Khi cần thiết, app được chuyển lên máy chủ công ty. Cloudflare Pages không dùng vì không chạy được Django.

Hệ quả cần biết:

- Trưởng GA và giám đốc chỉ vào được app khi laptop IT đang bật và cùng mạng LAN công ty (truy cập qua địa chỉ IP của laptop). Laptop tắt, mang ra ngoài hoặc hỏng thì không ai dùng được.
- Khi GA hoặc giám đốc bắt đầu dùng thường xuyên là thời điểm nên chuyển lên máy chủ công ty.
- Gói PostgreSQL free thường giới hạn dung lượng và có thể tạm dừng khi không dùng. Cần bật SSL, giới hạn IP truy cập nếu dịch vụ hỗ trợ, và chạy pg\_dump định kỳ về máy công ty.
- Ghi rõ các bước cài đặt (hoặc đóng gói Docker) để việc chuyển lên máy chủ chỉ là cài lại app và trỏ vào cùng cơ sở dữ liệu.

**Môi trường:** dev và production cùng nằm trên laptop IT nhưng tách hai cơ sở dữ liệu: PostgreSQL local để phát triển, PostgreSQL online cho dữ liệu thật, mỗi bên một file cấu hình. Không thử code mới trên dữ liệu thật.

## Kế hoạch chuyển đổi dữ liệu từ Excel

IT nhập tay toàn bộ dữ liệu, theo thứ tự từ danh mục gốc đến giao dịch, vì bảng sau phụ thuộc bảng trước. Excel chỉ ngừng dùng khi đối chiếu số lượng khớp 100%.

1. **Đóng băng Excel:** chốt một ngày, chuyển các file sang chỉ đọc. Mọi thay đổi phát sinh sau ngày đó ghi thẳng vào app (hoặc ghi vào một sheet "phát sinh" duy nhất nếu app chưa có module đó).
2. **Làm sạch trước khi nhập**, theo quy tắc chung:
   - Ngày tháng nhập theo định dạng chuẩn của app, không gõ số serial Excel.
   - Trạng thái chọn từ danh sách cố định thay vì chữ tự do ("Delivered to Mr. Chuong" → trạng thái Đang mượn + người mượn).
   - Màu ô trong Excel được chuyển thành trường dữ liệu tường minh.
   - Không nhập các cột mật khẩu.
3. **Nhập theo thứ tự:** phòng ban → nhân viên → mã hợp đồng (KHCM-…) và thiết bị trong hợp đồng → loại tài sản → tài sản (serial, HWID, MAC) → thiết bị đang cho mượn → license & gán license → phòng & thẻ → mượn thẻ hiện tại.
4. **Đối chiếu:** so số lượng trên app với Excel cho từng nhóm, ví dụ tổng PC/màn hình theo từng hợp đồng KHCM khớp sheet "PC\_Qty summary", 13 license Trend Micro với 5 đang dùng, 8 thẻ đang cho mượn. Ghi kết quả vào biên bản đối chiếu.
5. **Xác nhận:** trưởng GA kiểm tra phần thẻ ra vào; một giám đốc xem thử trang tổng quan.
6. **Cut-over:** ngừng dùng Excel, lưu trữ bản cuối ở thư mục chỉ đọc (đã xóa cột mật khẩu), thông báo cho người dùng.

Nhập liệu qua trang admin của Django là cách nhanh nhất cho một người. Nếu số bản ghi lớn hơn dự kiến, có thể bổ sung chức năng import CSV sau mà không ảnh hưởng thiết kế.

## Lộ trình triển khai

Dự án đi qua 6 giai đoạn nối tiếp, với 3 cổng kiểm soát phải đạt trước khi sang giai đoạn sau.

&#91;embedded content: lộ trình · 6 giai đoạn, 3 cổng kiểm soát\]

Thời lượng từng giai đoạn chưa được ước lượng; IT điền mốc ngày sau khi BRD được duyệt.

## Rủi ro và quyết định đã chốt

Rủi ro lớn nhất là chỉ một người vừa phát triển, nhập liệu vừa bảo trì. Kế hoạch giảm thiểu tập trung vào tài liệu, Git và bản pg\_dump để dựng lại app.

| Rủi ro | Mức | Giảm thiểu |
| --- | --- | --- |
| Chỉ một người IT: nghỉ phép dài hoặc nghỉ việc thì không ai vận hành được | Cao | README, hướng dẫn backup/khôi phục, code trên Git, bản pg\_dump mới nhất để dựng lại app trên máy khác |
| App chạy trên laptop IT: laptop tắt hoặc rời văn phòng thì người khác không truy cập được | Cao | Chuyển lên máy chủ công ty khi GA/giám đốc bắt đầu dùng thường xuyên |
| Mất hoặc bị trộm laptop (chứa chuỗi kết nối tới dữ liệu thật) | Cao | Bật BitLocker, mật khẩu Windows mạnh; mất máy thì đổi ngay mật khẩu cơ sở dữ liệu |
| Gói PostgreSQL free: tạm dừng, giới hạn dung lượng, không SLA, dữ liệu ở nước ngoài | Trung bình | Backup hằng ngày về máy công ty; xin xác nhận của ban giám đốc trước khi đặt dữ liệu nhân viên trên cloud |
| Nhập tay sai hoặc thiếu | Trung bình | Làm sạch trước, đối chiếu số lượng, GA xác nhận phần thẻ |
| Phình phạm vi (thêm cảnh báo, điện thoại giữa chừng) | Trung bình | Mọi yêu cầu mới ghi vào danh sách đợt sau, không chen vào đợt 1 |
| Mật khẩu đang nằm trong Excel dùng chung | Cao | Xóa các cột mật khẩu và đổi các mật khẩu đã lộ ngay, không chờ app |
| Bản dịch tiếng Nhật chưa tự nhiên | Thấp | Nhờ một giám đốc người Nhật duyệt file dịch trước UAT |

**Nhật ký quyết định:**

| Ngày | Quyết định |
| --- | --- |
| 2026-10-05 | Công nghệ: Django + PostgreSQL |
| 2026-10-05 | IT là người phát triển, bảo trì và nhập liệu duy nhất |
| 2026-10-05 | Phân quyền RBAC: IT toàn quyền và tạo người dùng; người dùng khác giới hạn theo Đ/G/S/X |
| 2026-10-05 | Xóa mềm cho mọi bản ghi nghiệp vụ |
| 2026-10-05 | Chuyển đổi dữ liệu bằng nhập tay; ngừng Excel khi nhập xong |
| 2026-10-05 | Chưa xây hệ thống cảnh báo và giao diện điện thoại |
| 2026-10-05 | Hạ tầng: app chạy trên laptop IT + PostgreSQL online; chuyển lên máy chủ công ty khi cần |
| 2026-10-05 | Giao diện: trang admin Django giữ CSS mặc định; trang tự viết dùng HTML thuần, thêm CSS sau |
| 2026-10-05 | Không quản lý nhà thầu; thẻ cho người bên ngoài mượn ghi tên, công ty bằng chữ |
| 2026-10-05 | Hợp đồng chỉ lưu mã, thiết bị, số lượng, tình trạng nhận và giao |
| 2026-10-05 | Tài sản có 3 trạng thái: Trong kho, Đang mượn, Mất; MAC là một cột thông tin |
| 2026-10-05 | Đợt 1 đăng nhập bằng tài khoản Django, HTTP trong LAN; SSO và HTTPS khi lên máy chủ |
| 2026-10-05 | Dev và production tách hai cơ sở dữ liệu trên cùng laptop |
