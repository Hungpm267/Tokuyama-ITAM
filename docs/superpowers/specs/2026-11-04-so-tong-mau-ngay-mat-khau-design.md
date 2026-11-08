# Sổ tổng: tô màu dòng, sửa ngày bàn giao, cột mật khẩu rõ ràng, dọn ghi chú nhập Excel

Ngày: 04/11/2026. Trạng thái: chờ người dùng duyệt.

## Bối cảnh và lý do

Sổ tổng (`/admin/so-tong`) là màn hình chính thay cho sheet Excel "List of TVC Employees". Người dùng là IT
Admin, vào công ty sau những người đang giữ máy. Bốn vấn đề hiện tại:

1. **Không tự đánh dấu được máy.** Trong Excel cũ, họ tô màu dòng để nhận ra máy riêng cho MES và máy không bị
   cài Zscaler. Sổ tổng hiện tự tô vàng khi ghi chú của máy có chữ "MES" (`ledger_service._row_kind`), người
   dùng không chọn được, không có chú giải.
2. **Ngày bàn giao là ngày giả.** Lúc nhập Excel, 51 lượt bàn giao đang mở được gán ngày tạm (16/10/2026 và
   02/11/2026) vì không ai biết ngày thật. Cột không sửa được, và database bắt buộc phải có ngày.
3. **Cột mật khẩu mơ hồ.** Hiện chỉ có một cờ "đã có mật khẩu" gộp chung, không biết là mật khẩu PC hay email.
4. **Ghi chú rác.** Agent đã tự ghi chú vào máy và lượt bàn giao khi nhập Excel. Người dùng muốn xóa, chỉ giữ
   một dòng ngắn ở những chỗ có thông tin thật.

## Mục tiêu

- Người dùng tự tạo kiểu đánh dấu (tên + màu tùy ý), gắn cho từng máy; cả dòng đổi màu; có chú giải (legend).
- Sửa được ngày bàn giao trên Sổ tổng, và xóa trống được khi không biết ngày.
- Cột mật khẩu ghi rõ: Không có / PC / Email / PC + Email.
- Dọn sạch ghi chú agent tự ghi và 51 ngày bàn giao tạm trên dữ liệu thật.

## Không làm

- Không hiện mật khẩu thật ở Sổ tổng. Xem mật khẩu vẫn chỉ qua kho mật khẩu và `RevealGate`.
- Không cho một máy mang nhiều màu cùng lúc.
- Không đổi luật bàn giao / thu hồi, không đổi trạng thái máy.

## Điều sẽ là thất bại dù chạy được

- Mật khẩu hoặc cột `*_enc` lọt ra response, CSV, log, audit.
- Xóa nhầm ghi chú do người dùng tự viết (ví dụ "my ntoe") hoặc ngày bàn giao người dùng đã tự nhập.
- Đổi ngày bàn giao làm máy đổi người giữ, hoặc làm hỏng luật "chỉ một lượt đang mở mỗi máy".
- Người chỉ có quyền xem mà sửa được màu hoặc ngày.

## 1. Tô màu dòng theo kiểu đánh dấu

### Người dùng quyết định

- Màu do người dùng tự đặt, kèm chú giải.
- Mỗi máy tối đa **một** kiểu đánh dấu. Máy MES và máy không cài Zscaler là hai kiểu riêng, dù máy MES vốn
  không cài Zscaler.
- Đánh dấu thuộc về **máy**, không thuộc về người: máy đổi người giữ vẫn giữ màu.

### Hành vi

- **Quản lý kiểu đánh dấu** ngay trên Sổ tổng: thêm, đổi tên, đổi màu, xóa. Chọn màu bằng bảng chọn màu của
  trình duyệt (`<input type="color">`).
- **Gắn cho máy**: một cột "Đánh dấu" trên Sổ tổng, sửa bằng ô chọn (danh sách kiểu đánh dấu + "Không đánh
  dấu"). Cũng chọn được trong bảng chi tiết bên phải (panel) nếu panel đang có ô sửa thông tin máy.
- **Màu dòng**: nền cả dòng là màu của kiểu đánh dấu. Chữ phải đọc được trên nền đó (tự chọn chữ tối/sáng
  theo độ sáng của màu, hoặc làm nhạt màu nền; builder chọn).
- **Chú giải** phía trên bảng: mỗi kiểu đánh dấu là một ô màu kèm tên và số máy đang mang. Bấm vào thì lọc
  bảng theo kiểu đó, bấm lại thì bỏ lọc. Trên điện thoại, chú giải vẫn hiện và thẻ (card) của dòng mang màu.
- **Xóa kiểu đánh dấu** đang có máy dùng: hỏi xác nhận, nói rõ số máy sẽ mất màu, rồi gỡ đánh dấu khỏi các máy
  đó. Xóa là xóa mềm như mọi bảng khác.
- Dòng **người đã nghỉ không giữ máy** vẫn tô xám như hiện nay. Nếu một dòng có máy mang đánh dấu, màu đánh dấu
  thắng.
- Bỏ luật tự tô vàng theo chữ "MES" trong ghi chú; tám máy MES được gắn sẵn kiểu "Máy MES" khi dọn dữ liệu
  (mục 4).
- Mọi thay đổi (tạo / sửa / xóa kiểu, gắn / gỡ trên máy) ghi audit.
- Quyền: sửa cần quyền `assets:change`; người chỉ xem thấy màu và chú giải nhưng không sửa được.

### Lưu ở đâu (lựa chọn của agent)

Dùng lại `asset_tags` (đã có cột `color`) và `asset_tag_links`, theo đúng nguyên tắc của BRD: nhãn thay cho
các cột boolean kiểu `is_mes_machine`, thêm nhãn là INSERT chứ không phải migration. Phân biệt với nhãn phần
mềm (`SW-…`) bằng quy ước mã: kiểu đánh dấu có mã bắt đầu `MARK-`, mã tự sinh từ tên, người dùng không phải
gõ. "Mỗi máy tối đa một đánh dấu" kiểm ở tầng service. Nếu builder thấy cần ràng buộc ở DB (ví dụ thêm cột
`kind` vào `asset_tags` để làm partial unique), được phép, nhưng phải cập nhật `docs/database.dbml`.

Màn hình SQLAdmin hiện có cho nhãn (`AssetTag`) không được để lộ việc sửa nhầm nhãn `MARK-` thành nhãn phần
mềm hay ngược lại; builder kiểm tra form đó.

## 2. Sửa / xóa trống ngày bàn giao

### Người dùng quyết định

- Sửa được ngày, và xóa trống được. Trống nghĩa là **máy vẫn ở chỗ người đó, chỉ không rõ ngày giao**.

### Hành vi

- Cột "Ngày bàn giao" trên Sổ tổng sửa được ở dòng có lượt bàn giao đang mở. Dòng không có lượt bàn giao thì
  ô không sửa được.
- Ô trống hiển thị trống (không "—" giả ngày).
- Không cho ngày ở tương lai (theo `today_local()`, UTC+7). Lượt đã trả: ngày giao không được sau ngày trả
  (CHECK `returned_after_borrowed` đã có, giữ nguyên ý nghĩa khi ngày giao là NULL).
- Bàn giao mới qua app vẫn tự lấy ngày hôm nay như cũ (người dùng vẫn sửa được sau).
- Sửa ngày chỉ đổi `borrowed_at` của lượt đang mở, không tạo lượt mới, không đổi máy / người. Ghi audit.
- Form SQLAdmin của lượt bàn giao cũng phải chấp nhận ô ngày trống.
- Sắp xếp theo cột ngày: dòng trống nằm cuối.
- Không cho ngày giao của lượt đang mở rơi vào trước ngày trả của lượt trước đó trên cùng máy (tránh lịch sử
  chồng nhau). Kiểm này dùng chung luật chống trùng lịch sử bàn giao đã có. (Lựa chọn của agent.)
- Form SQLAdmin để trống ngày thì lưu NULL, nghĩa là "không rõ ngày". Chỉ nghiệp vụ bàn giao trên Sổ tổng
  / nút bàn giao mới tự điền ngày hôm nay. (Lựa chọn của agent.)
- Quyền: `assignments:change`.

### Thay đổi schema

`assignments.borrowed_at` đổi thành cho phép NULL, migration `0006`. Cập nhật `models.py`, `database.dbml`,
và mọi chỗ code đang giả định ngày luôn có (định dạng ngày, so sánh ngày, sắp xếp lịch sử bàn giao, xuất CSV,
trang chi tiết máy / người). Builder rà toàn bộ.

## 3. Cột mật khẩu ghi rõ loại

- Giá trị: **Không có**, **PC**, **Email**, **PC + Email** (ba ngôn ngữ vi / en / ja).
- "Có" nghĩa là cột `*_enc` tương ứng trong `person_secrets` khác NULL. Chỉ đọc cờ có / không, không bao giờ
  đọc hay trả giá trị đã mã hóa.
- Chỉ người có quyền xem kho mật khẩu mới thấy cột này (giữ như `include_secret_flag` hiện nay). Dòng chỉ có
  máy, không có người: ô trống.
- Lọc được theo cột này như các cột khác.

## 4. Dọn dữ liệu đợt nhập Excel (chạy một lần trên Aiven)

Số liệu lấy từ bản sao lưu 02/11/2026 (`C:\Users\hungm\itam-backups\aiven-before-0005-*.dump`); script phải tự
tìm lại theo nội dung, không dựa vào id.

- **51 ngày bàn giao tạm**: lượt đang mở có ghi chú bắt đầu "Ngày bàn giao tạm" và ngày là 16/10/2026 hoặc
  02/11/2026 → đặt `borrowed_at = NULL`. Hai lượt ngày 20/09 và 19/10 không có ghi chú tạm, giữ nguyên.
- **Ghi chú trên lượt bàn giao** (53 dòng: "Ngày bàn giao tạm (…) - cần sửa theo ngày thực tế. Nhập từ file
  Excel." và 2 dòng máy dùng chung) → xóa trống.
- **Ghi chú trên máy**:
  - "Đã bàn giao từ dữ liệu file Excel (ngày bàn giao tạm)." (49 máy) → xóa trống.
  - 8 máy "Người dùng theo file Excel: MES system PC 0x. …" → gắn kiểu đánh dấu "Máy MES" (màu vàng như hiện
    nay), ghi chú rút còn "MES system PC 0x". (Giữ số PC là lựa chọn của agent: đó là tên gọi máy trong Excel,
    xóa đi thì mất.)
  - Máy dùng chung và máy của người đã nghỉ (người dùng chọn: giữ một dòng ngắn):
    - "Máy dùng chung General Affairs - Ms Tiên quản lý"
    - "Máy dùng chung phòng Tài chính - Ms Thoan quản lý"
    - "Máy dùng chung QA - Sakurai quản lý"
    - "Máy dùng chung Mua hàng - Phạm Cù Phương Thảo quản lý"
    - "Máy dùng chung Nhân sự - Phạm Huy Chương quản lý" (thông tin này đang nằm ở ghi chú lượt bàn giao, chuyển
      sang ghi chú máy)
    - "Người dùng cũ: Takata Yusuke (TVC00004), đã nghỉ", tương tự cho Nguyen Trung Hieu (TVC00005) và Yuki
      Asada (TVC00009)
  - Ghi chú khác (ví dụ "my ntoe") giữ nguyên.
- Tạo sẵn hai kiểu đánh dấu: "Máy MES" (vàng) và "Không cài Zscaler" (màu do builder chọn, người dùng đổi sau).
  Chưa gắn "Không cài Zscaler" cho máy nào.
- Script chỉ đổi dòng còn khớp **chính xác** nội dung lúc nhập Excel (ghi chú đúng nguyên văn, ngày đúng
  16/10 hoặc 02/11). Dòng đã bị người dùng sửa thì bỏ qua và liệt kê trong báo cáo, không dừng cả script.
  Một ngày tạm mà người dùng đã tự đổi sang ngày khác coi như ngày người dùng nhập, giữ nguyên. (Lựa chọn của
  agent.)
- Bản sao lưu 02/11 chỉ có nhãn `SW-`. Nếu lúc chạy trên Aiven có nhãn khác không phải `SW-` / `MARK-`, script
  để nguyên và báo ra. (Lựa chọn của agent.)
- Script có chế độ chạy thử (in ra những gì sẽ đổi, rollback) và chế độ ghi; ghi audit cho từng thay đổi;
  chạy thử trên bản khôi phục local của bản sao lưu trước.
- **Chạy trên Aiven chỉ khi người dùng cho phép rõ ràng**, sau khi sao lưu lại. Thứ tự lên production:
  sao lưu → migration `0006` → merge `main` vào `master` và chờ Render deploy xong (Render deploy từ `master`)
  → script dọn dữ liệu. Code cũ không chịu được ngày NULL, nên script chỉ chạy sau khi code mới đã lên; chỉ cho
  phép NULL thôi thì code cũ vẫn chạy được. (Lựa chọn của agent.)

## Ràng buộc

- Giữ mọi bất biến trong `CLAUDE.md`: xóa mềm, audit, `today_local()`, `app/core/inputs.py` cho endpoint JSON,
  không lộ `REDACTED_FIELDS`, giao diện ba ngôn ngữ, giao diện điện thoại.
- Test viết trước, xem đỏ rồi mới sửa. Toàn bộ test và `ruff` phải sạch.
- Kiểm tra trên trình duyệt sau khi sửa giao diện.

## Để builder quyết định

- Bố cục cụ thể của hộp quản lý kiểu đánh dấu, chỗ đặt chú giải, cách làm chữ đọc được trên nền màu.
- API cụ thể (đường dẫn, hình dạng JSON) cho kiểu đánh dấu và ngày bàn giao.
- Cột "Đánh dấu" có hiện mặc định không, rộng bao nhiêu.
