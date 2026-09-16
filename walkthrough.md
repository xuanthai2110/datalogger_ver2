# Tổng quan Dự án Datalogger (Phiên bản NoSmartLogger)

Dự án này là một hệ thống **Datalogger** (Bộ thu thập dữ liệu) chuyên dụng cho các hệ thống năng lượng mặt trời. Hệ thống được thiết kế để chạy trên các thiết bị nhúng (như Raspberry Pi) nhằm giám sát, thu thập dữ liệu và điều khiển các thiết bị biến tần (Inverter) từ nhiều hãng khác nhau.

Điểm đặc biệt của phiên bản này là khả năng quản lý và điều khiển cấp Dự án (Project) ngay cả khi hệ thống **không có bộ điều khiển trung tâm SmartLogger**, bằng cách trực tiếp phân bổ lệnh xuống từng Inverter thành phần.

---

## 1. Chức năng chính

### 📡 Thu thập dữ liệu (Telemetry)
- **Quét thiết bị (Scanning):** Tự động tìm kiếm các Inverter trong mạng RS485/Modbus.
- **Polling:** Thu thập dữ liệu thời gian thực (Điện áp, Dòng điện, Công suất, Nhiệt độ...) từ các Inverter theo chu kỳ.
- **Theo dõi giá trị Max:** Duy trì và cập nhật các giá trị cực đại trong ngày (Vmax, Pmax, Imax) và tự động reset vào đầu ngày mới.

### 🔄 Đồng bộ hóa Đám mây (Cloud Sync)
- **Đồng bộ cấu hình:** Tự động gửi thông tin Dự án và Inverter lên máy chủ Cloud.
- **Cơ chế Smart Diff:** Chỉ gửi các thay đổi (Patch) thay vì gửi toàn bộ dữ liệu, giúp tiết kiệm băng thông.
- **Hàng đợi Outbox:** Lưu trữ dữ liệu telemetry cục bộ và đẩy lên Cloud khi có kết nối internet, đảm bảo không mất dữ liệu.

### 🎮 Điều khiển công suất (Power Control)
- **Lập lịch (Scheduling):** Nhận lệnh điều khiển từ Cloud (MQTT) để giới hạn công suất theo thời gian.
- **Fallback NoSmartLogger:** Nếu không có SmartLogger, hệ thống tự động tính toán và chia đều/chia theo tỷ lệ công suất định mức xuống từng Inverter để đạt được tổng công suất mong muốn của toàn dự án.
- **An toàn:** Tự động khôi phục công suất 100% khi lịch trình kết thúc hoặc bị hủy.

### 🌐 Quản lý cục bộ (Local Management)
- **Web Interface:** Cung cấp giao diện web để người dùng cấu hình mạng, quét thiết bị và theo dõi trạng thái tại chỗ.
- **Multi-Tenant:** Hỗ trợ quản lý nhiều Dự án (Project) trên cùng một thiết bị Datalogger.

---

## 2. Kiến trúc Hệ thống

### 🗄️ Cơ sở dữ liệu (SQLite)
- `metadata.db`: Lưu cấu hình tĩnh (Thông tin dự án, danh sách inverter, cấu hình driver).
- `realtime.db`: Lưu dữ liệu động (Dữ liệu thời gian thực, hàng đợi outbox gửi tin).

### 🛠️ Các dịch vụ chính (Backend Services)
- **PollingService:** Chịu trách nhiệm giao tiếp Modbus để đọc dữ liệu từ thiết bị.
- **TelemetryService:** Xử lý, đóng gói và lưu trữ dữ liệu telemetry vào hàng đợi.
- **UploaderService:** Đẩy dữ liệu từ hàng đợi lên máy chủ Cloud qua REST API.
- **ControlService:** Thực hiện các lệnh điều khiển công suất (P, Q, Cosphi).
- **SetupService:** Quản lý việc đồng bộ cấu hình giữa Local và Cloud.
- **SyncWorker/LogicWorker:** Các tiến trình chạy nền xử lý logic nghiệp vụ và đồng bộ hóa.

### 🔌 Drivers
- Hỗ trợ nhiều dòng Inverter phổ biến: **Huawei**, **Sungrow**, **Goodwe**, **Growatt**... thông qua các driver Modbus tùy chỉnh.

---

## 3. Cấu trúc Thư mục

- `/backend`: Mã nguồn chính của ứng dụng (Python).
  - `/api`: Các điểm cuối REST API cục bộ.
  - `/drivers`: Thư viện giao tiếp với các loại thiết bị.
  - `/services`: Logic nghiệp vụ của hệ thống.
  - `/workers`: Các tiến trình xử lý nền.
- `/deploy`: Các tệp tin cấu hình triển khai (Docker, Script cài đặt).
- `docker-compose.yml`: Cấu hình chạy ứng dụng dưới dạng container.

---

## 4. Quy trình hoạt động chuẩn

1. **Khởi tạo:** Người dùng cấu hình dự án và quét tìm Inverter qua giao diện Web.
2. **Đồng bộ:** Datalogger gửi yêu cầu phê duyệt dự án/inverter lên Cloud.
3. **Giám sát:** `PollingService` liên tục đọc dữ liệu -> `TelemetryService` lưu vào DB -> `UploaderService` gửi lên Cloud.
4. **Điều khiển:** Khi có lịch từ Cloud gửi xuống -> `ControlService` phân bổ lệnh xuống Inverter -> Báo cáo trạng thái về Cloud.

---
*Tài liệu này được tổng hợp dựa trên mã nguồn hiện tại của dự án.*
