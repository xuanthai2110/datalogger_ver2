import sys
import time
import argparse
import logging
from datetime import datetime

# Tránh lỗi UnicodeEncodeError trên Windows CMD/PowerShell khi in tiếng Việt
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Cấu hình logging cơ bản
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ModbusSniffer")

# Thử import serial, nếu chưa cài thì hướng dẫn cài đặt
try:
    import serial
except ImportError:
    logger.error("Thư viện 'pyserial' chưa được cài đặt. Vui lòng cài bằng lệnh: pip install pyserial")
    sys.exit(1)

def parse_env_file(filepath=".env"):
    """Đọc file .env thủ công để lấy cấu hình cổng COM mặc định"""
    config = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    config[key.strip()] = val.strip()
    except Exception:
        pass
    return config

def calculate_crc16(data: bytes) -> int:
    """Tính mã CRC16 Modbus"""
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 1) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

def check_crc(data: bytes) -> bool:
    """Kiểm tra xem dữ liệu có khớp CRC16 không (2 byte cuối)"""
    if len(data) < 3:
        return False
    return calculate_crc16(data) == 0

def parse_modbus_frame(frame: bytes):
    """
    Phân tích gói tin Modbus RTU cơ bản:
    Trả về: (loại_gói, chi_tiết)
    loại_gói: 'Request' (Master gửi) hoặc 'Response' (Slave phản hồi) hoặc 'Unknown'
    """
    if len(frame) < 4:
        return "Unknown", "Gói quá ngắn"

    slave_id = frame[0]
    func_code = frame[1]
    length = len(frame)

    # Function Codes phổ biến:
    # 03 (0x03): Read Holding Registers
    # 04 (0x04): Read Input Registers
    # 06 (0x06): Write Single Register
    # 16 (0x10): Write Multiple Registers
    
    if func_code in (3, 4):
        # Request luôn dài đúng 8 byte: [Slave_ID, Func, Start_Addr_H, Start_Addr_L, Regs_H, Regs_L, CRC_L, CRC_H]
        if length == 8:
            start_addr = (frame[2] << 8) | frame[3]
            regs_count = (frame[4] << 8) | frame[5]
            return "Request", f"Master đọc {regs_count} thanh ghi từ địa chỉ {start_addr} (Slave ID: {slave_id})"
        # Response: [Slave_ID, Func, Byte_Count, Data..., CRC_L, CRC_H]
        # Độ dài Response = 3 + Byte_Count + 2 = 5 + Byte_Count
        elif length >= 5:
            byte_count = frame[2]
            if length == 5 + byte_count:
                return "Response", f"Slave {slave_id} trả về {byte_count} bytes dữ liệu"
            
    elif func_code == 6:
        # Write Single Register: Request và Response đều dài 8 byte và giống nhau
        if length == 8:
            reg_addr = (frame[2] << 8) | frame[3]
            value = (frame[4] << 8) | frame[5]
            return "Request/Response", f"Ghi thanh ghi đơn: Địa chỉ {reg_addr}, Giá trị: {value} (Slave ID: {slave_id})"
            
    elif func_code == 16: # 0x10
        # Request: [Slave_ID, Func, Start_Addr_H, Start_Addr_L, Regs_H, Regs_L, Byte_Count, Data..., CRC_L, CRC_H]
        # Dài = 7 + Byte_Count + 2 = 9 + Byte_Count
        if length >= 9:
            byte_count = frame[6]
            if length == 9 + byte_count:
                start_addr = (frame[2] << 8) | frame[3]
                regs_count = (frame[4] << 8) | frame[5]
                return "Request", f"Master ghi nhiều thanh ghi: Từ {start_addr}, Số lượng {regs_count} (Slave ID: {slave_id})"
        # Response: [Slave_ID, Func, Start_Addr_H, Start_Addr_L, Regs_H, Regs_L, CRC_L, CRC_H] (8 bytes)
        elif length == 8:
            start_addr = (frame[2] << 8) | frame[3]
            regs_count = (frame[4] << 8) | frame[5]
            return "Response", f"Slave {slave_id} xác nhận ghi xong {regs_count} thanh ghi từ {start_addr}"

    return "Unknown", f"Mã hàm {func_code}, độ dài {length} bytes"

def lookup_db_port(port_name: str):
    """
    Tìm kiếm thông tin cổng com_port và baudrate từ CSDL metadata.db.
    Hỗ trợ các tên như 'RS485_0', 'RS485_1', v.v.
    """
    import sqlite3
    import os
    db_paths = [
        os.path.join("backend", "db_manager", "data", "metadata.db"),
        os.path.join("backend", "db_manager", "metadata.db"),
        "metadata.db"
    ]
    for db_path in db_paths:
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # Tìm theo tên driver (ví dụ: 'RS485_0') hoặc theo id
                cursor.execute(
                    "SELECT com_port, baudrate FROM comm_config WHERE driver = ? OR id = ?",
                    (port_name, port_name)
                )
                row = cursor.fetchone()
                conn.close()
                if row:
                    return row["com_port"], row["baudrate"]
            except Exception as e:
                logger.warning(f"Lỗi khi truy vấn CSDL {db_path}: {e}")
    return None, None

def main():
    # Lấy cấu hình mặc định từ file .env
    env_config = parse_env_file()
    default_port = env_config.get("MODBUS_PORT", "COM1") # Trên Windows thường dùng COMx, Linux là /dev/ttyUSBx
    default_baud = int(env_config.get("MODBUS_BAUDRATE", "9600"))

    parser = argparse.ArgumentParser(description="Script nghe lén và phân tích tần suất gửi tin của Master trên đường truyền RS485.")
    parser.add_argument("-p", "--port", default=default_port, help=f"Cổng Serial kết nối hoặc tên kênh cấu hình (Ví dụ: RS485_0, COM1, /dev/ttyUSB0)")
    parser.add_argument("-b", "--baud", type=int, default=default_baud, help=f"Tốc độ Baudrate (mặc định từ .env hoặc từ CSDL: {default_baud})")
    parser.add_argument("-t", "--timeout-gap", type=float, default=0.035, help="Khoảng thời gian im lặng (giây) để xác định kết thúc gói tin Modbus (mặc định: 0.035s)")
    args = parser.parse_args()

    # Thử phân giải tên kênh cấu hình từ CSDL (ví dụ: RS485_0)
    db_port, db_baud = lookup_db_port(args.port)
    actual_port = args.port
    actual_baud = args.baud
    
    if db_port:
        actual_port = db_port
        actual_baud = db_baud
        print(f"[+] Đã tìm thấy cấu hình cho kênh '{args.port}' trong CSDL: port='{db_port}', baudrate={db_baud}")
    else:
        # Nếu nhập trực tiếp cổng COM nhưng không có trong DB thì giữ nguyên cấu hình truyền vào
        pass

    print("=========================================================================")
    print("        SCRIPT NGHE LÉN VÀ PHÂN TÍCH TẦN SUẤT GỬI CỦA MASTER KHÁC        ")
    print("=========================================================================")
    print(f"[*] Cổng kết nối vật lý: {actual_port}")
    print(f"[*] Tốc độ Baud        : {actual_baud}")
    print(f"[*] Cấu hình gap       : {args.timeout_gap * 1000:.1f} ms")
    print("[*] Hướng dẫn           : Đảm bảo Datalogger của ta đang TẮT (dừng service) để không làm nhiễu kết quả nghe lén.")
    print("                         Nhấn Ctrl+C để dừng nghe lén và xem thống kê tần suất.")
    print("=========================================================================")

    try:
        ser = serial.Serial(
            port=actual_port,
            baudrate=actual_baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.005 # Đọc từng chunk nhỏ liên tục
        )
    except Exception as e:
        logger.error(f"Không thể mở cổng serial {actual_port}: {e}")
        return

    last_master_req_time = None
    master_intervals = []
    
    buffer = bytearray()
    last_byte_time = time.time()
    in_packet = False

    total_valid_frames = 0
    total_master_requests = 0
    total_slave_responses = 0

    try:
        while True:
            # Đọc dữ liệu thô từ cổng COM
            data = ser.read(64)
            now = time.time()

            if data:
                if not in_packet:
                    in_packet = True
                buffer.extend(data)
                last_byte_time = now
            else:
                # Nếu đã có dữ liệu và khoảng thời gian im lặng vượt quá timeout-gap
                if in_packet and (now - last_byte_time >= args.timeout_gap):
                    packet = bytes(buffer)
                    # Reset các trạng thái để nhận gói tiếp theo
                    buffer = bytearray()
                    in_packet = False

                    # Kiểm tra CRC gói tin
                    is_valid = check_crc(packet)
                    timestamp_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                    if is_valid:
                        total_valid_frames += 1
                        frame_type, detail = parse_modbus_frame(packet)
                        hex_str = packet.hex().upper()
                        # Tách chuỗi hex cho dễ nhìn
                        hex_formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))

                        if "Request" in frame_type:
                            total_master_requests += 1
                            interval_str = ""
                            if last_master_req_time is not None:
                                interval = now - last_master_req_time
                                master_intervals.append(interval)
                                interval_str = f" | Khoảng cách lệnh trước: {interval:.3f}s"
                            last_master_req_time = now
                            
                            print(f"[{timestamp_str}] [MASTER -> SLAVE] {detail}")
                            print(f"      Raw: {hex_formatted}{interval_str}")
                        elif "Response" in frame_type:
                            total_slave_responses += 1
                            print(f"[{timestamp_str}] [SLAVE -> MASTER] {detail}")
                            print(f"      Raw: {hex_formatted}")
                        else:
                            print(f"[{timestamp_str}] [MODBUS VALID] Type: {frame_type} | {detail}")
                            print(f"      Raw: {hex_formatted}")
                    else:
                        # Gói tin bị lỗi CRC hoặc là nhiễu / va chạm đường truyền
                        hex_str = packet.hex().upper()
                        hex_formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
                        print(f"[{timestamp_str}] [NHIỄU / SAI CRC] Raw: {hex_formatted}")

    except KeyboardInterrupt:
        print("\n\n=========================================================================")
        print("                        THỐNG KÊ KẾT QUẢ NGHE LÉN                         ")
        print("=========================================================================")
        print(f"[-] Tổng số gói tin Modbus hợp lệ nhận được: {total_valid_frames}")
        print(f"[-] Số gói tin Master yêu cầu (Request)     : {total_master_requests}")
        print(f"[-] Số gói tin Slave phản hồi (Response)    : {total_slave_responses}")
        
        if master_intervals:
            avg_interval = sum(master_intervals) / len(master_intervals)
            min_interval = min(master_intervals)
            max_interval = max(master_intervals)
            print(f"[-] Tần suất gửi yêu cầu của Master khác:")
            print(f"    * Khoảng cách trung bình giữa các lệnh: {avg_interval:.3f} giây (tương đương {1/avg_interval:.2f} Hz)")
            print(f"    * Khoảng cách ngắn nhất giữa các lệnh : {min_interval:.3f} giây")
            print(f"    * Khoảng cách dài nhất giữa các lệnh  : {max_interval:.3f} giây")
            
            # Phân tích xem có khả năng chạy theo chu kỳ polling không
            # Ví dụ: nếu có khoảng cách lớn (>1s) xen kẽ khoảng cách nhỏ, có thể đó là khoảng nghỉ giữa các vòng quét (Cycle)
            long_intervals = [x for x in master_intervals if x > 1.0]
            if long_intervals:
                avg_cycle = sum(long_intervals) / len(long_intervals)
                print(f"    * Dự đoán chu kỳ quét toàn bộ (Cycle): ~{avg_cycle:.1f} giây")
        else:
            print("[-] Không thu thập đủ dữ liệu khoảng cách giữa các lệnh của Master để tính tần suất.")
        print("=========================================================================")
    finally:
        try:
            ser.close()
            print("[*] Đã đóng cổng serial.")
        except Exception:
            pass

if __name__ == "__main__":
    main()
