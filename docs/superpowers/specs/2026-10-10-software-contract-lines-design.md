# Hạng mục hợp đồng cho Phần mềm — Thiết kế

Ngày: 10/10/2026 · Trạng thái: đã được người dùng duyệt trong phiên làm việc

## 1. Vấn đề

Phần hợp đồng hiện chỉ phục vụ thiết bị vật lý:

- Số "đã nhận" của một hạng mục được đếm từ `assets.contract_line_id`. Hạng mục mua
  phần mềm không có thiết bị nào để gắn nên không bao giờ nhận đủ; hợp đồng chỉ mua
  phần mềm mãi ở trạng thái `PENDING`.
- Màn hình "Nhập kho theo lô" chỉ hỏi serial, mã GA, mã KDDI, model.
- `licenses` chỉ nối tới `contracts` (không tới hạng mục), và ô đó cũng không có trên form.

## 2. Mục tiêu và phạm vi

Nhập một hợp đồng mua phần mềm tự nhiên như hợp đồng mua máy, và tiến độ giao hàng
của hợp đồng phản ánh đúng cả phần mềm.

Quyết định đã chốt với người dùng:

| # | Quyết định |
|---|---|
| 1 | Phần mềm vẫn nằm ở phân hệ License; chỉ nối gói license vào hạng mục hợp đồng. Danh sách Thiết bị vẫn chỉ gồm đồ vật lý. |
| 2 | Loại hạng mục hiển thị là "Phần cứng" / "Phần mềm" (không ghi "License"). Các menu License hiện có giữ nguyên tên. |
| 3 | Số lượng của hạng mục phần mềm là **số seat**. Đã nhận = tổng seat của các gói gắn vào. |
| 4 | Đợt này chỉ làm phần mềm. Đồ vật lý không serial (cáp, chuột) để đợt sau. |

Ngoài phạm vi: nhập license key trên màn hình nhận (chưa có luồng nhập key mã hoá nào
trong app); đổi tên menu License; đồ vật lý không serial.

## 3. Thay đổi schema (migration Alembic `0003`)

| Bảng | Thay đổi |
|---|---|
| `contract_lines` | Thêm `item_kind` ENUM native `contract_item_kind` (`HARDWARE`, `SOFTWARE`), `NOT NULL DEFAULT 'HARDWARE'`. Hạng mục cũ giữ nguyên là phần cứng. |
| `licenses` | Thêm `contract_line_id` FK → `contract_lines.id` (`RESTRICT`, nullable, có index). |

`licenses.contract_id` giữ lại; khi gói gắn vào hạng mục, `contract_id` được điền theo
hợp đồng của hạng mục đó.

Phương án đã loại: (a) không có cột loại, suy ra từ thứ được gắn vào — trước khi nhận
hàng không biết mở màn hình nào; (b) bảng "đợt nhận hàng" đa hình — quá nặng.

## 4. Cách tính "đã nhận"

Không có cột số lượng gõ tay (giữ Rule 8). Một hàm duy nhất
`contract_service.line_received_qty(db, line)`:

- `HARDWARE`: `COUNT(assets)` còn sống có `contract_line_id = line.id`.
- `SOFTWARE`: `SUM(licenses.seats)` còn sống có `contract_line_id = line.id`.

`sync_contract_delivery_status` và mọi chỗ kiểm tra số lượng đều dùng hàm này.
`ContractLine.qty_delivered` (dùng để hiển thị) tính theo cùng quy tắc.

## 5. Quy tắc nghiệp vụ

1. Không nhận vượt: tổng seat sau khi lưu ≤ `qty_ordered`.
2. Thiết bị không gắn được vào hạng mục `SOFTWARE`; gói license không gắn được vào hạng mục `HARDWARE`.
3. Không đổi `item_kind` khi hạng mục đã có hàng nhận.
4. Không giảm `qty_ordered` xuống dưới số đã nhận.
5. Không xóa hạng mục đã có thiết bị hoặc gói license còn sống.
6. Sửa seat / đổi hạng mục / xóa / khôi phục gói license → tính lại tiến độ hợp đồng
   (cả hợp đồng cũ và mới). Khôi phục làm vượt số lượng thì từ chối.
7. Nhận phần mềm cần quyền `(licenses, add)`; sai quyền trả 403 chung.
8. Hạng mục hoặc hợp đồng đã xóa mềm thì không nhận hàng được.

## 6. Giao diện

- **Form Hạng mục hợp đồng**: thêm ô chọn "Loại hạng mục".
- **Danh sách / chi tiết Hạng mục**: thêm cột loại; nút "Nhận hàng" của dòng phần mềm
  dẫn tới màn hình nhận phần mềm.
- **Màn hình nhận phần mềm** `GET/POST /admin/contract-line/{id}/receive-software`:
  chọn sản phẩm phần mềm, số seat (mặc định = số còn lại), ngày kích hoạt, ngày hết hạn,
  ghi chú; hiện đã nhận / tổng đặt mua. Lưu tạo một `License` gắn sẵn hạng mục, ghi
  audit `CREATE`, đồng bộ tiến độ hợp đồng.
- Mở `.../receive` (phần cứng) trên hạng mục phần mềm thì chuyển hướng sang màn hình
  phần mềm; POST nhập serial vào hạng mục phần mềm bị từ chối 400.
- **Form / chi tiết Gói license**: thêm ô "Hạng mục hợp đồng" để gắn các gói đã nhập từ trước.
- Nhãn mới có đủ vi / en / ja.

## 7. Thành phần

| File | Việc |
|---|---|
| `alembic/versions/0003_software_contract_lines.py` | migration |
| `app/enums.py`, `app/models.py` | `ContractItemKind`, cột và quan hệ mới |
| `app/services/contract_service.py` | `line_received_qty`, đồng bộ dùng chung |
| `app/services/license_service.py` | `receive_license_for_line` |
| `app/routers/software_receive.py` + `templates/sqladmin/software_receive.html` | màn hình nhận phần mềm |
| `app/routers/batch_receive.py` | từ chối / chuyển hướng hạng mục phần mềm |
| `app/admin.py` | form, cột, formatter, các quy tắc ở mục 5 |
| `app/routers/trash.py` | kiểm tra và đồng bộ khi khôi phục gói license |
| `app/core/i18n.py` | nhãn mới |

## 8. Kiểm thử

Viết test trước (`tests/test_software_contract_lines.py`) cho từng quy tắc mục 4 và 5 và
cho màn hình nhận phần mềm qua HTTP. Toàn bộ bộ test hiện có phải giữ xanh; migration
được kiểm qua `alembic upgrade head` trong fixture test.
