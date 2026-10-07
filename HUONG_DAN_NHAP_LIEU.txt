================================================================================
          HƯỚNG DẪN QUY TRÌNH & THỨ TỰ NHẬP LIỆU HỆ THỐNG ITAM
                     CÔNG TY TNHH TOKUYAMA VIETNAM
================================================================================

Địa chỉ truy cập: http://localhost:8000/admin
Tài khoản mặc định:
- Tên đăng nhập: it.admin
- Mật khẩu: Admin@Tokuyama2026

--------------------------------------------------------------------------------
A. NGUYÊN TẮC VÀNG VỀ THỨ TỰ NHẬP LIỆU (QUAN TRỌNG NHẤT)
--------------------------------------------------------------------------------
Trong cơ sở dữ liệu quan hệ, dữ liệu cấp con (ví dụ: máy tính được giao cho ai) 
bắt buộc phải có dữ liệu cấp cha (phòng ban, danh mục, nhân viên) trước đó.

NẾU NHẬP NGƯỢC THỨ TỰ, hệ thống sẽ không có danh sách lựa chọn (dropdown trống) 
hoặc báo lỗi ràng buộc toàn vẹn dữ liệu.

Thứ tự nhập chuẩn được chia thành 5 GIAI ĐOẠN nối tiếp nhau dưới đây:


================================================================================
B. THỨ TỰ NHẬP LIỆU CHI TIẾT (TỪ BƯỚC 1 ĐẾN BƯỚC 5)
================================================================================

--------------------------------------------------------------------------------
BƯỚC 1: KHỞI TẠO CÁC DANH MỤC DÙNG CHUNG (CẦN NHẬP ĐẦU TIÊN)
--------------------------------------------------------------------------------
Đây là các bảng gốc làm dữ liệu nguồn cho toàn bộ hệ thống:

1.1. Phòng ban (Menu: "Danh mục" -> "Phòng ban")
     - Ý nghĩa: Danh sách các phòng ban của Tokuyama Vietnam.
     - Các trường cần nhập:
       + Name En: Tên tiếng Anh (vd: Production, General Affairs, Accounting, IT)
       + Name Ja: Tên tiếng Nhật (vd: 製造部, 総務部, 経理部)

1.2. Danh mục thiết bị (Menu: "Danh mục" -> "Danh mục thiết bị")
     - Ý nghĩa: Các phân loại phần cứng IT trong công ty.
     - Các trường cần nhập:
       + Name En: Laptop, Desktop, Monitor, Printer, Network Switch...
       + Name Ja: ノートPC, デスクトップPC, モニター, プリンター...

1.3. Vị trí & Phòng ốc (Menu: "Danh mục" -> "Vị trí & Phòng ốc")
     - Ý nghĩa: Nơi đặt thiết bị hoặc vị trí các cửa quẹt thẻ.
     - Các trường cần nhập:
       + Building: Tên tòa nhà/khu vực (vd: Office, Factory A, Gate)
       + Floor: Tầng (vd: 1F, 2F)
       + Room En: Tên phòng tiếng Anh (vd: Server Room, Meeting Room 1, GA Office)
       + Room Ja: Tên phòng tiếng Nhật (vd: サーバー室, 会議室1)
       + Is access controlled: Tích chọn nếu phòng này có khóa thẻ từ

1.4. Nhãn tài sản (Menu: "Danh mục" -> "Nhãn tài sản") - Tùy chọn
     - Ý nghĩa: Nhãn phân loại đặc thù (vd: VIP, Dùng chung, Máy dự phòng...)
     - Nhập Code (vd: VIP, SHARED, SPARE) và Name En.

1.5. Sản phẩm License phần mềm (Menu: "License" -> "Sản phẩm phần mềm")
     - Ý nghĩa: Danh sách tên các ứng dụng mua bản quyền.
     - Nhập Name (vd: Trend Micro Apex One, Microsoft 365 Business, AutoCAD LT)
     - Nhập Vendor: Nhà cung cấp phần mềm.


--------------------------------------------------------------------------------
BƯỚC 2: NHẬP HỒ SƠ NHÂN SỰ & DANH BẠ THOẠI
--------------------------------------------------------------------------------
Sau khi đã có "Phòng ban" ở Bước 1:

2.1. Nhân sự (Menu: "Nhân sự" -> "Hồ sơ nhân sự")
     - Các trường cần nhập:
       + Staff code: Mã nhân viên (BẮT BUỘC DUY NHẤT, vd: TVC00001, TVC00025)
       + Full name: Họ và tên nhân viên (vd: Nguyễn Văn An, Tanaka Taro)
       + Department: Chọn phòng ban tương ứng từ danh sách
       + Email: Địa chỉ email công ty (vd: an.nv@tokuyama.vn)
       + Status: Trạng thái nhân viên (Chọn ACTIVE: đang làm việc, hoặc RESIGNED: đã nghỉ)

2.2. Danh bạ điện thoại (Menu: "Danh bạ thoại" -> "Danh bạ điện thoại") - Tùy chọn
     - Gán số máy bàn (Extension) hoặc số di động cho từng nhân sự.


--------------------------------------------------------------------------------
BƯỚC 3: NHẬP HỢP ĐỒNG MUA SẮM IT (NẾU CÓ THEO DÕI HỢP ĐỒNG)
--------------------------------------------------------------------------------
Phục vụ đối soát số lượng thiết bị mua trên giấy tờ so với thực tế nhận kho:

3.1. Hợp đồng (Menu: "Hợp đồng" -> "Hợp đồng mua sắm")
     - Nhập Contract no (Số hợp đồng), Vendor name (Nhà cung cấp), Signed at (Ngày ký).

3.2. Dòng hợp đồng (Menu: "Hợp đồng" -> "Chi tiết dòng hợp đồng")
     - Chọn hợp đồng cha, nhập tên sản phẩm, số lượng mua (Quantity) và đơn giá.
     - LƯU Ý: Không tự gõ số lượng đã giao; hệ thống sẽ tự động đếm số máy nhập 
       ở Bước 4 liên kết với dòng hợp đồng này.


--------------------------------------------------------------------------------
BƯỚC 4: NHẬP TÀI SẢN THIẾT BỊ, THẺ RA VÀO & BẢN QUYỀN
--------------------------------------------------------------------------------
Khi đã có "Danh mục", "Nhân sự" và "Hợp đồng":

4.1. Thiết bị IT (Menu: "Tài sản" -> "Tài sản thiết bị")
     - Các trường cần nhập:
       + Asset code: Mã quản lý nội bộ (vd: TVC-E00027, TKY-PC0105)
       + Serial: Số Serial phần cứng của hãng sản xuất (BẮT BUỘC DUY NHẤT, vd: 5CD1234XYZ)
       + Category: Chọn danh mục phần cứng (Laptop, Desktop...)
       + Status: Trạng thái ban đầu (thường là IN_STOCK: Trong kho, hoặc IN_USE)
       + Contract line: Chọn dòng hợp đồng đã mua máy này (nếu có)
       + Model / Spec: Cấu hình tóm tắt (vd: Dell Latitude 5420, i5/16GB/512GB)

4.2. Thẻ ra vào (Menu: "Thẻ ra vào" -> "Thẻ ra vào")
     - Nhập Card no (Mã in trên thẻ, vd: CARD-001, CARD-002).
     - Trạng thái Status: AVAILABLE (Sẵn sàng cấp/cho mượn) hoặc ASSIGNED.

4.3. Giấy phép phần mềm (Menu: "License" -> "Giấy phép bản quyền")
     - Chọn Product (từ Bước 1.5).
     - Nhập Seats: Số lượng máy/người được phép kích hoạt (vd: 50).
     - Ngày bắt đầu (Starts at) và Ngày hết hạn (Expires at).


--------------------------------------------------------------------------------
BƯỚC 5: NGHIỆP VỤ CẤP PHÁT & MƯỢN TRẢ (VẬN HÀNH HÀNG NGÀY)
--------------------------------------------------------------------------------
Khi có phát sinh giao nhận máy, thẻ từ hoặc gán bản quyền:

5.1. Bàn giao thiết bị cho nhân viên (Menu: "Tài sản" -> "Lịch sử cấp phát")
     - Chọn Asset (Thiết bị cần giao).
     - Chọn Person (Nhân viên nhận máy).
     - Assigned at: Ngày bàn giao máy.
     - Returned at: ĐỂ TRỐNG (nghĩa là nhân viên đang giữ máy).
     - Khi nhân viên trả máy / nghỉ việc: Chỉ cần mở lại dòng này và điền ngày 
       trả vào ô "Returned at" (KHÔNG ĐƯỢC XÓA BẢN GHI LỊCH SỬ NÀY).

5.2. Cho mượn thẻ ra vào (Menu: "Thẻ ra vào" -> "Lịch sử mượn thẻ")
     - Chọn Thẻ (Card).
     - Chọn Người mượn: Là nhân viên công ty (Borrower person) HOẶC nhập tên 
       nhà thầu/khách bên ngoài (External borrower name).
     - Borrowed at: Ngày mượn.
     - Returned at: ĐỂ TRỐNG cho đến khi khách/nhân viên trả lại thẻ.

5.3. Cấp phát License (Menu: "License" -> "Cấp phát License")
     - Gán gói bản quyền cho một Thiết bị (Asset) hoặc Nhân sự (Person) cụ thể.


================================================================================
C. CÁC QUY TẮC RÀNG BUỘC TOÀN VẸN CẦN LƯU Ý ĐỂ KHÔNG BỊ LỖI
================================================================================

1. NGUYÊN TẮC "MỘT THIẾT BỊ CHỈ CÓ 1 NGƯỜI GIỮ TẠI MỘT THỜI ĐIỂM":
   - Nếu máy tính A đang được nhân viên B mượn (chưa điền ngày Returned at), 
     hệ thống sẽ TỪ CHỐI nếu bạn cố tình tạo thêm dòng cấp phát máy A cho nhân viên C.
   - Muốn cấp máy A cho người mới: Phải cập nhật ngày "Returned at" cho nhân viên cũ trước.

2. NGUYÊN TẮC DUY NHẤT CỦA SỐ SERIAL VÀ MÃ NHÂN VIÊN:
   - Serial máy và Mã nhân viên không được trùng với bất kỳ bản ghi nào đang hoạt động.
   - Trường hợp máy cũ đã thanh lý (đã xóa mềm), số serial đó mới được phép tái sử dụng.

3. NGUYÊN TẮC BẢO VỆ LỊCH SỬ:
   - Các bảng: "Lịch sử cấp phát", "Lịch sử mượn thẻ", "Nhật ký kiểm toán" 
     KHÔNG BAO GIỜ ĐƯỢC PHÉP XÓA. Dữ liệu này là bằng chứng bàn giao tài sản.

4. NGUYÊN TẮC XÓA MỀM (SOFT DELETE):
   - Khi xóa một thiết bị hoặc một nhân sự, hệ thống không xóa hẳn khỏi cơ sở dữ liệu 
     mà chuyển sang trạng thái ẩn và BẮT BUỘC PHẢI NHẬP LÝ DO XÓA (Delete reason).

5. AN TOÀN MẬT KHẨU NHÂN VIÊN:
   - Mật khẩu lưu trữ tại "Mật khẩu nhân viên" được tự động mã hóa bằng thuật toán 
     AES-256-GCM. Không ai xem được trực tiếp trừ khi thực hiện quy trình mở khóa (Reveal) 
     và xác minh lại mật khẩu của chính quản trị viên.


================================================================================
TÓM TẮT SƠ ĐỒ DÒNG DỮ LIỆU:
  [Phòng ban] ---------> [Hồ sơ nhân sự] --------\
                                                  +---> [Cấp phát Thiết bị]
  [Danh mục] -----------> [Tài sản thiết bị] -----/
  [Hợp đồng] ------------/
================================================================================
