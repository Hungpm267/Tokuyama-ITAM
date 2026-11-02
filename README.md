# Hướng dẫn sử dụng — Hệ thống Quản lý Tài sản IT Tokuyama Việt Nam

Phần mềm này thay cho file Excel danh sách nhân viên và laptop. Nó giúp bạn biết **ai đang giữ máy nào, máy nào có phần mềm gì**, và ai đã làm gì trên hệ thống.

Tài liệu này dành cho người dùng phần mềm. Bạn không cần biết gì về lập trình.

## Mục lục

1. [Bắt đầu](#1-bắt-đầu)
2. [Sổ tổng](#2-sổ-tổng)
3. [Thiết bị: bàn giao, thu hồi](#3-thiết-bị-bàn-giao-thu-hồi)
4. [Nhân sự](#4-nhân-sự)
5. [Kho mật khẩu nhân sự](#5-kho-mật-khẩu-nhân-sự)
6. [Xóa và khôi phục](#6-xóa-và-khôi-phục)
7. [Tài khoản](#7-tài-khoản)
8. [Nhật ký thao tác](#8-nhật-ký-thao-tác)
9. [Khi phần mềm báo lỗi](#9-khi-phần-mềm-báo-lỗi)

---

## 1. Bắt đầu

### Đăng nhập

1. Mở trình duyệt (Chrome hoặc Edge) và vào địa chỉ mà bộ phận IT đã cung cấp.
2. Nhập **tên đăng nhập** và **mật khẩu**, rồi bấm **Đăng nhập**.

Nếu bạn không thao tác gì trong **30 phút**, phần mềm tự đăng xuất để bảo vệ dữ liệu. Chỉ cần đăng nhập lại.

### Đổi ngôn ngữ

Bấm vào tên ngôn ngữ ở góc trên bên phải và chọn **Tiếng Việt**, **English** hoặc **日本語**. Toàn bộ màn hình và các thông báo đổi theo ngay.

### Bạn làm được gì

Phần mềm có hai mức sử dụng. Bạn chỉ thấy những nút mình được phép dùng.

| Mức | Dành cho | Được làm |
| :--- | :--- | :--- |
| **Quản trị viên** | Chuyên viên IT | Mọi việc: sửa dữ liệu, bàn giao, thu hồi, xem kho mật khẩu, quản lý tài khoản, khôi phục dữ liệu đã xóa. |
| **Chỉ xem** | Trưởng phòng GA, Ban Giám đốc | Xem Sổ tổng, thiết bị, nhân sự và lịch sử bàn giao. Ban Giám đốc xem thêm được nhật ký thao tác. |

---

## 2. Sổ tổng

Đây là trang đầu tiên sau khi đăng nhập: một bảng giống file Excel, gồm mọi laptop kèm người giữ. Nhân viên chưa có máy cũng có một dòng.

- **Xem:** kéo ngang để xem các cột. Cột Tên máy và Người giữ luôn được ghim.
- **Tìm:** gõ vào ô tìm kiếm trên cùng, hoặc ô lọc dưới mỗi tiêu đề cột.
- **Lọc nhanh:** Tất cả, Đang dùng, Trong kho, Đã nghỉ.
- **Sắp xếp:** bấm vào tiêu đề cột. Nút **Cột** để ẩn hoặc hiện cột.
- **Sửa:** bấm đúp vào ô để sửa số serial, mã GA, ghi chú, email, userId, phòng ban.
- **Copy:** kéo chọn vùng ô rồi `Ctrl + C`, dán được sang Excel.
- **Xuất Excel:** tải về đúng các dòng đang lọc.
- **Màu hàng:** xám là người đã nghỉ, vàng là máy MES.

Bấm biểu tượng ⓘ đầu dòng để mở bảng bên phải: lịch sử máy, nút **Bàn giao**, **Thu hồi**, và đánh dấu phần mềm trên máy. Người giữ và trạng thái máy không sửa trực tiếp trong ô; hãy dùng hai nút này để giữ được lịch sử.

Muốn thêm một phần mềm vào danh sách đánh dấu, vào **Danh mục Nhãn** tạo nhãn có mã bắt đầu bằng `SW-`.

---

## 3. Thiết bị: bàn giao, thu hồi

Vào **Tài sản → Danh sách Thiết bị**.

### Trạng thái của một thiết bị

| Trạng thái | Ý nghĩa |
| :--- | :--- |
| **Trong kho** | Sẵn sàng bàn giao. |
| **Đang sử dụng** | Đang có một nhân viên giữ. |
| **Đang sửa chữa** | Máy hỏng, đang bảo hành hoặc chờ sửa. |
| **Đã thanh lý** | Không còn dùng nữa. |
| **Mất** | Thất lạc. |

Trạng thái **Đang sử dụng** do phần mềm tự đặt khi bạn bàn giao, và tự gỡ khi bạn thu hồi. Bạn không chọn tay được trạng thái này.

### Thêm một thiết bị

1. Bấm **Thêm mới** ở góc trên bên phải.
2. Chọn **loại tài sản** và nhập ít nhất một trong ba mã: mã GA, mã KDDI hoặc số serial.
3. Bấm **Lưu**.

### Bàn giao máy cho nhân viên

1. Ở dòng của máy đang **Trong kho**, bấm **Bàn giao**.
2. Chọn nhân viên nhận máy.
3. Chọn ngày bàn giao (mặc định là hôm nay; không chọn được ngày trong tương lai) và ghi chú nếu cần.
4. Bấm xác nhận.

Máy chuyển sang **Đang sử dụng** và tên người giữ hiện ngay trên danh sách.

### Thu hồi máy

1. Ở dòng của máy đang **Đang sử dụng**, bấm **Thu hồi**. Nút này cũng có trong **Lịch sử Cấp phát Tài sản**.
2. Chọn ngày thu hồi.
3. Chọn tình trạng máy khi nhận lại: **Nhập lại kho** hoặc **Máy lỗi / hỏng** (cần sửa).
4. Bấm xác nhận.

### Xem lịch sử

**Tài sản → Lịch sử Cấp phát Tài sản** liệt kê mọi lượt bàn giao từ trước tới nay. Lượt đã thu hồi được giữ lại làm lịch sử: bạn chỉ đính chính được ngày và ghi chú, không đổi được sang máy khác hay người khác.

### Những điều phần mềm không cho phép

- Bàn giao máy đang sửa chữa, đã thanh lý hoặc bị mất.
- Bàn giao cho nhân viên đã nghỉ việc.
- Một máy có hai người giữ cùng lúc.
- Đổi trạng thái của máy đang có người giữ. Hãy thu hồi trước.
- Xóa máy đang có người giữ.

---

## 4. Nhân sự

Vào **Nhân sự → Hồ sơ Nhân sự**.

- Mỗi nhân viên có mã nhân viên, họ tên, phòng ban, email, ngày vào làm và tình trạng: **Sắp vào làm**, **Đang làm việc** hoặc **Đã nghỉ việc**.
- Mở trang chi tiết của một người để thấy các thiết bị họ đang giữ và đã từng giữ.

### Khi một nhân viên nghỉ việc

1. Mở trang chi tiết của người đó để xem họ còn giữ gì.
2. Thu hồi hết thiết bị.
3. Sau đó mới sửa tình trạng thành **Đã nghỉ việc**.

Nếu còn máy chưa thu hồi, phần mềm sẽ từ chối và cho biết còn bao nhiêu thiết bị.

---

## 5. Kho mật khẩu nhân sự

Chỉ **Quản trị viên** dùng được mục này (**Nhân sự → Kho Mật khẩu Nhân sự**). Nó lưu mật khẩu máy tính và email của nhân viên để phục vụ bàn giao và xử lý sự cố.

- Mật khẩu luôn hiện dưới dạng `••••••`.
- Muốn xem, bấm **Xem** rồi **nhập lại mật khẩu đăng nhập của chính bạn**.
- Sau khi xác nhận, bạn xem được mật khẩu trong vòng 2 phút mà không phải nhập lại. Mật khẩu đang hiện sẽ tự ẩn sau 60 giây.
- Nhập sai mật khẩu xác nhận 5 lần trong 15 phút thì chức năng xem bị khóa 15 phút.
- Mỗi lần xem đều được ghi vào nhật ký.
- Khi rời bàn làm việc, bấm nút **khóa phiên xem** màu đỏ để hủy quyền xem ngay.

---

## 6. Xóa và khôi phục

### Xóa

Bấm biểu tượng thùng rác ở đầu dòng, nhập lý do xóa (nên nhập để sau này tra lại), rồi xác nhận.

Dữ liệu đã xóa **không mất hẳn**: nó được chuyển vào Thùng rác.

Phần mềm không cho xóa những thứ đang được dùng, ví dụ nhân viên còn giữ máy, máy đang có người giữ, hoặc loại tài sản, phòng ban đang có bản ghi sử dụng.

Lịch sử bàn giao không xóa được.

### Khôi phục

Vào **Thùng rác** ở cuối menu (cần có quyền), tìm bản ghi và bấm **Khôi phục**.

Phần mềm sẽ từ chối khôi phục nếu việc đó tạo ra dữ liệu sai, ví dụ số serial đã được dùng cho một máy khác.

---

## 7. Tài khoản

Phần này dành cho Quản trị viên, ở mục **Tài khoản Đăng nhập** trong nhóm menu **Hệ thống & Phân quyền**: tạo tài khoản, đặt lại mật khẩu (tối thiểu 6 ký tự), chọn nhóm và ngôn ngữ, tạm khóa một tài khoản.

Bạn không thể tự khóa tài khoản của mình hoặc tự đổi nhóm của mình; việc đó phải do một Quản trị viên khác làm.

---

## 8. Nhật ký thao tác

Vào **Truy vết → Audit Trail**. Mọi thao tác đều được ghi lại: ai làm, lúc nào, trên bản ghi nào, giá trị trước và sau khi sửa. Nhật ký này không ai sửa hay xóa được, kể cả Quản trị viên.

Bạn có thể lọc theo loại thao tác (tạo, sửa, xóa, đăng nhập, xem mật khẩu…).

---

## 9. Khi phần mềm báo lỗi

Phần lớn thông báo là phần mềm đang ngăn một thao tác không hợp lý. Bảng dưới là các trường hợp hay gặp.

| Thông báo hoặc tình huống | Lý do | Cách xử lý |
| :--- | :--- | :--- |
| Thiết bị đang được bàn giao cho người khác | Máy chưa được thu hồi từ người đang giữ. | Thu hồi máy trước, rồi bàn giao lại. |
| Không thể bàn giao thiết bị ở trạng thái… | Máy đang sửa, đã thanh lý hoặc bị mất. | Sửa trạng thái máy về Trong kho nếu máy đã dùng lại được. |
| Hãy thu hồi thiết bị trước khi đổi trạng thái | Bạn đang đổi trạng thái của máy có người giữ. | Bấm **Thu hồi**, khi thu hồi chọn luôn tình trạng máy. |
| …đã tồn tại trong hệ thống | Mã, số serial hoặc tên này đã có. Chữ hoa và chữ thường được coi là như nhau. | Kiểm tra lại mã. Nếu bản ghi cũ đã bị xóa nhầm, vào Thùng rác để khôi phục. |
| …không được ở tương lai | Ngày bàn giao, thu hồi không được sau hôm nay. | Chọn hôm nay hoặc một ngày đã qua. |
| Còn đang giữ … thiết bị | Bạn đang chuyển một nhân viên sang Đã nghỉ việc. | Thu hồi hết rồi mới đổi tình trạng. |
| Không thể xóa vì đang có … sử dụng bản ghi này | Loại tài sản, phòng ban… vẫn đang được dùng. | Chuyển các bản ghi đó sang giá trị khác trước. |
| Lượt … đã đóng, không thể đổi… | Bạn đang đổi máy hoặc người của một dòng lịch sử. | Lịch sử chỉ đính chính được ngày và ghi chú. Nếu ghi nhầm người, tạo một lượt mới đúng. |
| Không thấy nút Bàn giao | Tài khoản của bạn không có quyền đó. | Liên hệ Quản trị viên. |
| Bị đưa về màn hình đăng nhập | Quá 30 phút không thao tác. | Đăng nhập lại. |
| "Internal Server Error" hoặc lỗi lạ | Sự cố kỹ thuật. | Ghi lại bạn đang làm gì, chụp màn hình và gửi cho bộ phận IT. |

---

*Cần hỗ trợ, vui lòng liên hệ Quản trị viên IT của công ty.*

*Dành cho người phát triển: xem `CLAUDE.md` và `HANDOVER.md`.*
