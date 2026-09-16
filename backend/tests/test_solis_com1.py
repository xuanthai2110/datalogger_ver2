import sys
import logging
from datetime import datetime

# Thêm đường dẫn project vào sys.path để import các module của backend
sys.path.append(".")

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TestSolis")

from backend.communication.modbus_rtu import ModbusRTU
from backend.drivers.inverters.solis_100k import Solis100k
from backend.services.normalization_service import NormalizationService

def main():
    port = "/dev/ttyUSB1"      # Cổng COM kết nối bộ chuyển đổi RS485-to-USB
    baudrate = 9600    # Baudrate mặc định của giao thức Solis

    logger.info(f"Khởi tạo kết nối Modbus RTU trên cổng {port} (Baudrate={baudrate})...")

    transport = ModbusRTU(
        port=port,
        baudrate=baudrate,
        parity="N",
        stopbits=1,
        bytesize=8,
        timeout=2.0,      # Timeout 2 giây để tránh bị lỗi mất gói tin trên đường truyền dài
        retries=3
    )

    if not transport.connect():
        logger.error(f"Lỗi: Không thể kết nối tới cổng {port}.")
        return

    for slave_id in range(1, 9):
        try:
            driver = Solis100k(transport, slave_id=slave_id)
            
            # Đọc thanh ghi dsp_version (địa chỉ tài liệu 3001 -> địa chỉ code 3000) và ir (địa chỉ tài liệu 3092 -> địa chỉ code 3091)
            regs = [
                {"name": "dsp_version", "address": 3000, "length": 1, "type": "uint16", "scale": None},
                {"name": "ir", "address": 3091, "length": 1, "type": "uint16", "scale": 1}
            ]
            data = driver._read_group(regs)

            # Chuẩn hoá dữ liệu
            normalization = NormalizationService()
            clean_data = normalization.normalize(data)

            ir_val = clean_data.get("ir")
            dsp_version = clean_data.get("dsp_version")
            
            # Định dạng hiển thị DSP version dưới dạng hex (Ví dụ: 0x0207 -> "0207")
            dsp_version_hex = f"{int(dsp_version):04X}" if dsp_version is not None else "N/A"
            
            print(f"[Slave ID {slave_id}] DSP Version: {dsp_version_hex} (Raw: {dsp_version}) | Điện trở cách điện (IR): {ir_val} kΩ")

        except Exception as e:
            logger.error(f"Slave ID {slave_id}: Lỗi khi đọc dữ liệu - {e}")
            continue

if __name__ == "__main__":
    main()
