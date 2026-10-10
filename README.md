# Hướng dẫn sử dụng — Hệ thống Quản lý Tài sản IT Tokuyama Việt Nam

Phần mềm này thay cho các file Excel trước đây. Nó giúp bạn biết **ai đang giữ máy nào, thẻ nào, phần mềm nào**, hợp đồng nào đã nhận đủ hàng, và ai đã làm gì trên hệ thống.

Tài liệu này dành cho người dùng phần mềm. Bạn không cần biết gì về lập trình.

## Mục lục

1. [Bắt đầu](#1-bắt-đầu)
2. [Làm quen với màn hình](#2-làm-quen-với-màn-hình)
3. [Thiết bị: nhập, bàn giao, thu hồi](#3-thiết-bị-nhập-bàn-giao-thu-hồi)
4. [Nhân sự](#4-nhân-sự)
5. [Phần mềm và bản quyền](#5-phần-mềm-và-bản-quyền)
6. [Hợp đồng mua sắm và nhận hàng](#6-hợp-đồng-mua-sắm-và-nhận-hàng)
7. [Thẻ ra vào](#7-thẻ-ra-vào)
8. [Danh bạ điện thoại](#8-danh-bạ-điện-thoại)
9. [Kho mật khẩu nhân sự](#9-kho-mật-khẩu-nhân-sự)
10. [Xóa và khôi phục](#10-xóa-và-khôi-phục)
11. [Xuất dữ liệu ra Excel](#11-xuất-dữ-liệu-ra-excel)
12. [Tài khoản và phân quyền](#12-tài-khoản-và-phân-quyền)
13. [Nhật ký thao tác](#13-nhật-ký-thao-tác)
14. [Khi phần mềm báo lỗi](#14-khi-phần-mềm-báo-lỗi)

---

## 1. Bắt đầu

### Đăng nhập

1. Mở trình duyệt (Chrome hoặc Edge) và vào địa chỉ mà bộ phận IT đã cung cấp.
2. Nhập **tên đăng nhập** và **mật khẩu**, rồi bấm **Đăng nhập**.

Nếu bạn không thao tác gì trong **30 phút**, phần mềm tự đăng xuất để bảo vệ dữ liệu. Chỉ cần đăng nhập lại.

### Đổi ngôn ngữ

Bấm vào tên ngôn ngữ ở góc trên bên phải và chọn **Tiếng Việt**, **English** hoặc **日本語**. Toàn bộ màn hình và các thông báo đổi theo ngay.

### Bạn làm được gì

Phần mềm có ba nhóm người dùng. Bạn chỉ thấy những mục và những nút mà mình được phép dùng.

| Nhóm | Dành cho | Được làm mặc định |
| :--- | :--- | :--- |
| **Quản trị viên** | Chuyên viên IT | Mọi việc: nhập và sửa dữ liệu, bàn giao, thu hồi, xem kho mật khẩu, quản lý tài khoản, khôi phục dữ liệu đã xóa. |
| **Trưởng phòng GA** | Phòng Tổng vụ | Quản lý nhân sự, thẻ ra vào và danh bạ điện thoại. Xem thiết bị, lịch sử bàn giao và hợp đồng. |
| **Ban Giám đốc** | Giám đốc | Chỉ xem: nhân sự, thiết bị, phần mềm, thẻ, hợp đồng, danh bạ và nhật ký thao tác. |

Quản trị viên có thể điều chỉnh quyền của từng nhóm hoặc của riêng một người (xem [mục 12](#12-tài-khoản-và-phân-quyền)).

---

## 2. Làm quen với màn hình

- **Menu bên trái** chia theo nhóm việc: Tài sản, License, Thẻ ra vào, Hợp đồng, Nhân sự, Danh bạ thoại…
- **Trang Tổng quan** (trang đầu tiên sau khi đăng nhập) cho thấy số thiết bị, số máy đang cấp phát và còn trong kho, cùng hai loại cảnh báo:
  - thẻ ra vào đã quá ngày hẹn trả;
  - bản quyền phần mềm sắp hết hạn trong 60 ngày hoặc đã hết hạn.
- **Tìm kiếm nhanh**: bấm `Ctrl + K` (hoặc bấm vào ô tìm kiếm trên cùng) rồi gõ mã máy, số serial, tên hoặc mã nhân viên, số thẻ, số hợp đồng, số máy nhánh. Kết quả hiện theo từng nhóm.
- **Trong mỗi danh sách**, ba biểu tượng ở đầu dòng là: con mắt để xem chi tiết, cây bút để sửa, thùng rác để xóa.

---

## 3. Thiết bị: nhập, bàn giao, thu hồi

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

Để nhập nhiều máy cùng lúc từ một hợp đồng, xem [mục 6](#6-hợp-đồng-mua-sắm-và-nhận-hàng).

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
- Thanh lý hoặc báo mất một máy còn đang được gán bản quyền phần mềm. Hãy thu hồi bản quyền trước.
- Xóa máy đang có người giữ hoặc đang được gán bản quyền.

---

## 4. Nhân sự

Vào **Nhân sự → Hồ sơ Nhân sự**.

- Mỗi nhân viên có mã nhân viên, họ tên, phòng ban, email, ngày vào làm và tình trạng: **Sắp vào làm**, **Đang làm việc** hoặc **Đã nghỉ việc**.
- Mở trang chi tiết của một người để thấy tất cả những gì họ đang giữ và đã từng giữ: thiết bị, bản quyền phần mềm, thẻ ra vào.

### Khi một nhân viên nghỉ việc

1. Mở trang chi tiết của người đó để xem họ còn giữ gì.
2. Thu hồi hết thiết bị, thẻ ra vào và bản quyền phần mềm.
3. Sau đó mới sửa tình trạng thành **Đã nghỉ việc**.

Nếu còn thứ chưa thu hồi, phần mềm sẽ từ chối và cho biết còn bao nhiêu thiết bị, thẻ, bản quyền.

---

## 5. Phần mềm và bản quyền

Phần mềm được quản lý ở nhóm menu **License**, **không** nằm trong danh sách thiết bị.

| Mục | Dùng để |
| :--- | :--- |
| **Danh mục Phần mềm** | Khai báo tên các phần mềm công ty dùng (Office, PDF, Trend Micro…). |
| **Kho License Phần mềm** | Mỗi dòng là một gói đã mua: bao nhiêu bản quyền, đã cấp bao nhiêu, còn trống bao nhiêu, ngày hết hạn. |
| **Phân bổ Bản quyền** | Ghi lại bản quyền nào đang cấp cho máy nào hoặc người nào. |

### Cấp bản quyền cho máy hoặc người

1. Vào **Phân bổ Bản quyền**, bấm **Thêm mới**.
2. Chọn gói bản quyền.
3. Chọn thiết bị, hoặc nhân viên, hoặc cả hai.
4. Nhập ngày gán. Nếu bản quyền này có hạn riêng cho từng máy, nhập thêm ngày hết hạn.
5. Bấm **Lưu**.

### Thu hồi bản quyền

Mở lượt gán đó ra sửa và nhập **thời điểm thu hồi**. Bản quyền được trả lại vào số còn trống.

### Cần biết

- Khi gói đã cấp hết, phần mềm không cho gán thêm.
- Gói **đã hết hạn** vẫn gán được, nhưng có dấu cảnh báo "đã hết hạn" ngay trong ô chọn và trên danh sách.
- Không giảm được tổng số bản quyền của một gói xuống thấp hơn số đang cấp.
- Không gán được cho máy đã thanh lý hoặc bị mất, và không gán cho nhân viên đã nghỉ việc.

---

## 6. Hợp đồng mua sắm và nhận hàng

### Tạo hợp đồng

1. Vào **Hợp đồng → Hợp đồng Mua sắm IT**, bấm **Thêm mới**, nhập số hợp đồng, nhà cung cấp và ngày ký.
2. Vào **Hợp đồng → Chi tiết Hạng mục**, thêm từng dòng hàng của hợp đồng đó:
   - chọn hợp đồng;
   - nhập tên hạng mục và số lượng đặt mua;
   - chọn **Loại hạng mục**: **Phần cứng** (máy tính, màn hình…) hoặc **Phần mềm** (bản quyền). Với phần mềm, số lượng là số bản quyền.

### Nhận hàng phần cứng

1. Ở dòng hạng mục, bấm **Nhận hàng**.
2. Chọn loại tài sản và nhập thông tin chung của lô (model…).
3. Nhập từng máy: số serial, mã GA hoặc mã KDDI. Có thể dán cả danh sách serial từ Excel.
4. Bấm xác nhận. Các máy được tạo trong **Danh sách Thiết bị**, ở trạng thái Trong kho.

### Nhận hàng phần mềm

1. Ở dòng hạng mục loại Phần mềm, bấm **Nhận phần mềm**.
2. Chọn sản phẩm phần mềm, nhập số bản quyền nhận đợt này, ngày kích hoạt và ngày hết hạn (để trống nếu là bản quyền vĩnh viễn).
3. Bấm xác nhận. Gói bản quyền xuất hiện trong **Kho License Phần mềm**.

Bạn có thể nhận thành nhiều đợt. Các đợt của cùng một sản phẩm và cùng hạn dùng được cộng vào một gói, không tạo thêm dòng mới.

### Tiến độ giao hàng

Phần mềm tự đếm số đã nhận và hiện tiến độ của từng hạng mục: **Chưa nhận**, **Giao một phần**, **Đã đủ hàng**. Hợp đồng được ghi là đã giao đủ khi mọi hạng mục đều đủ. Bạn không cần, và không thể, gõ tay các con số này.

Phần mềm không cho nhận vượt số lượng đặt mua. Nếu số lượng mua thật sự thay đổi, hãy sửa số lượng đặt mua của hạng mục trước.

---

## 7. Thẻ ra vào

- **Thẻ ra vào → Danh sách Thẻ từ**: mỗi thẻ có số thẻ, loại thẻ (nhân viên, nhà thầu, khách) và trạng thái (trong kho, đang cho mượn, bị mất, hỏng).
- **Thẻ ra vào → Sổ Mượn-Trả Thẻ**: ghi lại ai mượn thẻ nào, từ ngày nào.

### Cho mượn thẻ

1. Vào **Sổ Mượn-Trả Thẻ**, bấm **Thêm mới**.
2. Chọn thẻ.
3. Chọn nhân viên mượn, **hoặc** nhập tên và công ty của người bên ngoài. Chỉ điền một trong hai.
4. Nhập ngày mượn và ngày dự kiến trả.

Thẻ tự chuyển sang **Đang cho mượn**.

### Trả thẻ

Mở lượt mượn đó ra sửa và nhập **thời điểm trả**. Thẻ tự trở về **Trong kho**.

Thẻ đã báo mất hoặc hỏng thì không cho mượn được, và vẫn giữ nguyên trạng thái đó sau khi đóng lượt mượn. Thẻ quá ngày hẹn trả sẽ hiện trên trang Tổng quan.

---

## 8. Danh bạ điện thoại

Vào **Danh bạ thoại → Danh bạ & Thiết bị Điện thoại** để tra cứu và cập nhật số máy nhánh, loại thiết bị và vị trí đặt máy.

---

## 9. Kho mật khẩu nhân sự

Chỉ **Quản trị viên** dùng được mục này (**Nhân sự → Kho Mật khẩu Nhân sự**). Nó lưu mật khẩu máy tính và email của nhân viên để phục vụ bàn giao và xử lý sự cố.

- Mật khẩu luôn hiện dưới dạng `••••••`.
- Muốn xem, bấm **Xem** rồi **nhập lại mật khẩu đăng nhập của chính bạn**.
- Sau khi xác nhận, bạn xem được mật khẩu trong vòng 2 phút mà không phải nhập lại. Mật khẩu đang hiện sẽ tự ẩn sau 60 giây.
- Nhập sai mật khẩu xác nhận 5 lần trong 15 phút thì chức năng xem bị khóa 15 phút.
- Mỗi lần xem đều được ghi vào nhật ký.
- Khi rời bàn làm việc, bấm nút **khóa phiên xem** màu đỏ để hủy quyền xem ngay.

---

## 10. Xóa và khôi phục

### Xóa

Bấm biểu tượng thùng rác ở đầu dòng, nhập lý do xóa (nên nhập để sau này tra lại), rồi xác nhận.

Dữ liệu đã xóa **không mất hẳn**: nó được chuyển vào Thùng rác.

Phần mềm không cho xóa những thứ đang được dùng, ví dụ:

- nhân viên còn giữ máy, thẻ hoặc bản quyền;
- máy đang có người giữ;
- thẻ đang cho mượn;
- gói bản quyền đang cấp cho ai đó;
- hạng mục hợp đồng đã nhận hàng;
- loại tài sản, phòng ban hay sản phẩm phần mềm đang có bản ghi sử dụng.

Lịch sử bàn giao, lịch sử cấp bản quyền và sổ mượn thẻ không xóa được.

### Khôi phục

Vào **Thùng rác** ở cuối menu (cần có quyền), tìm bản ghi và bấm **Khôi phục**.

Phần mềm sẽ từ chối khôi phục nếu việc đó tạo ra dữ liệu sai, ví dụ số serial đã được dùng cho một máy khác, hoặc hạng mục hợp đồng đã nhận đủ bằng hàng thay thế.

---

## 11. Xuất dữ liệu ra Excel

Ở mỗi danh sách, bấm **Export** để tải về một file mở được bằng Excel.

- File có đúng các cột bạn đang thấy trên màn hình.
- Nếu bạn đang tìm kiếm hoặc lọc, file chỉ chứa các dòng khớp.
- Mật khẩu và mã bản quyền không bao giờ có trong file.

---

## 12. Tài khoản và phân quyền

Phần này dành cho Quản trị viên, trong nhóm menu **Hệ thống & Phân quyền**.

| Mục | Dùng để |
| :--- | :--- |
| **Tài khoản Đăng nhập** | Tạo tài khoản, đặt lại mật khẩu (tối thiểu 6 ký tự), chọn nhóm và ngôn ngữ, tạm khóa một tài khoản. |
| **Ma trận Quyền Vai trò** | Bật hoặc tắt quyền Xem, Thêm, Sửa, Xóa của từng nhóm trên từng phần. Có nút khôi phục về mặc định. |
| **Quyền riêng Người dùng** | Cấp thêm hoặc chặn bớt một quyền cho riêng một người mà không đổi nhóm của họ. |

Bạn không thể tự khóa tài khoản của mình hoặc tự đổi nhóm của mình; việc đó phải do một Quản trị viên khác làm.

---

## 13. Nhật ký thao tác

Vào **Truy vết → Audit Trail**. Mọi thao tác đều được ghi lại: ai làm, lúc nào, trên bản ghi nào, giá trị trước và sau khi sửa. Nhật ký này không ai sửa hay xóa được, kể cả Quản trị viên.

Bạn có thể lọc theo loại thao tác (tạo, sửa, xóa, đăng nhập, xem mật khẩu…).

---

## 14. Khi phần mềm báo lỗi

Phần lớn thông báo là phần mềm đang ngăn một thao tác không hợp lý. Bảng dưới là các trường hợp hay gặp.

| Thông báo hoặc tình huống | Lý do | Cách xử lý |
| :--- | :--- | :--- |
| Thiết bị đang được bàn giao cho người khác | Máy chưa được thu hồi từ người đang giữ. | Thu hồi máy trước, rồi bàn giao lại. |
| Không thể bàn giao thiết bị ở trạng thái… | Máy đang sửa, đã thanh lý hoặc bị mất. | Sửa trạng thái máy về Trong kho nếu máy đã dùng lại được. |
| Hãy thu hồi thiết bị trước khi đổi trạng thái | Bạn đang đổi trạng thái của máy có người giữ. | Bấm **Thu hồi**, khi thu hồi chọn luôn tình trạng máy. |
| …đã tồn tại trong hệ thống | Mã, số serial hoặc tên này đã có. Chữ hoa và chữ thường được coi là như nhau. | Kiểm tra lại mã. Nếu bản ghi cũ đã bị xóa nhầm, vào Thùng rác để khôi phục. |
| Bản quyền đã hết lượt gán | Gói đã cấp hết số bản quyền. | Thu hồi bản quyền từ máy không còn dùng, hoặc mua thêm. |
| …không được ở tương lai | Ngày bàn giao, thu hồi, mượn, trả không được sau hôm nay. | Chọn hôm nay hoặc một ngày đã qua. |
| Còn đang giữ … thiết bị, … thẻ, … bản quyền | Bạn đang chuyển một nhân viên sang Đã nghỉ việc. | Thu hồi hết rồi mới đổi tình trạng. |
| Không thể xóa vì đang có … sử dụng bản ghi này | Loại tài sản, phòng ban… vẫn đang được dùng. | Chuyển các bản ghi đó sang giá trị khác trước. |
| Hạng mục đặt mua …, đã nhận … | Bạn đang nhận vượt số lượng đặt mua. | Kiểm tra lại số lượng, hoặc sửa số lượng đặt mua của hạng mục. |
| Loại tài sản chỉ dành cho thiết bị vật lý | Bạn đang tạo loại tài sản cho phần mềm. | Quản lý phần mềm ở nhóm **License**. |
| Lượt … đã đóng, không thể đổi… | Bạn đang đổi máy hoặc người của một dòng lịch sử. | Lịch sử chỉ đính chính được ngày và ghi chú. Nếu ghi nhầm người, tạo một lượt mới đúng. |
| Không thấy nút Bàn giao, Nhận hàng… | Tài khoản của bạn không có quyền đó. | Liên hệ Quản trị viên. |
| Bị đưa về màn hình đăng nhập | Quá 30 phút không thao tác. | Đăng nhập lại. |
| "Internal Server Error" hoặc lỗi lạ | Sự cố kỹ thuật. | Ghi lại bạn đang làm gì, chụp màn hình và gửi cho bộ phận IT. |

---

*Cần hỗ trợ, vui lòng liên hệ Quản trị viên IT của công ty.*

*Dành cho người phát triển: xem `CLAUDE.md`, `GEMINI.md` và `HANDOVER.md`.*
