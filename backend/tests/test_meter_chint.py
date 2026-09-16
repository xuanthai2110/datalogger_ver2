import sys
import os
import logging
import json

# Thêm thư mục gốc vào PYTHONPATH để có thể import các module trong backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.communication.modbus_tcp import ModbusTCP
from backend.communication.modbus_rtu import ModbusRTU
from backend.drivers.meters.chint_dtsu666 import MeterChintDtsu666

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestChint")

def test_meter_tcp(host, port=502, slave_id=1):
    logger.info(f"--- Testing Chint DTSU666 via TCP: {host}:{port}, Slave: {slave_id} ---")
    transport = ModbusTCP(host=host, port=port, timeout=2, retries=2)
    
    if not transport.connect():
        logger.error("Failed to connect via TCP")
        return

    try:
        driver = MeterChintDtsu666(transport, slave_id=slave_id)
        
        # Thử đọc Serial Number
        sn = driver.read_serial_number()
        logger.info(f"Serial Number: {sn}")

        # Đọc toàn bộ dữ liệu
        data = driver.read_all()
        if data:
            logger.info("Successfully read data from meter:")
            print(json.dumps(data, indent=4))
        else:
            logger.error("Failed to read data from meter")
            
    finally:
        transport.close()

def test_meter_rtu(port, baudrate=9600, slave_id=1):
    logger.info(f"--- Testing Chint DTSU666 via RTU: {port}, Baud: {baudrate}, Slave: {slave_id} ---")
    transport = ModbusRTU(port=port, baudrate=baudrate, timeout=1, retries=2)
    
    if not transport.connect():
        logger.error(f"Failed to open port {port}")
        return

    try:
        driver = MeterChintDtsu666(transport, slave_id=slave_id)
        
        # Thử đọc Serial Number
        sn = driver.read_serial_number()
        logger.info(f"Serial Number: {sn}")

        # Đọc toàn bộ dữ liệu
        data = driver.read_all()
        if data:
            logger.info("Successfully read data from meter:")
            print(json.dumps(data, indent=4))
        else:
            logger.error("Failed to read data from meter")
            
    finally:
        transport.close()

if __name__ == "__main__":
    # Cấu hình từ người dùng: RTU, 9600, 8N1, /dev/ttyUSB0
    PORT = "/dev/ttyUSB0"
    BAUDRATE = 9600
    SLAVE_ID_START = 1
    SLAVE_ID_END = 10

    logger.info(f"Starting scan on {PORT} from Slave ID {SLAVE_ID_START} to {SLAVE_ID_END}...")
    
    transport = ModbusRTU(port=PORT, baudrate=BAUDRATE, timeout=0.5, retries=1)
    
    if not transport.connect():
        logger.error(f"Failed to open port {PORT}")
        sys.exit(1)

    try:
        found = False
        for slave_id in range(SLAVE_ID_START, SLAVE_ID_END + 1):
            logger.info(f"Checking Slave ID: {slave_id}...")
            driver = MeterChintDtsu666(transport, slave_id=slave_id)
            
            # Thử đọc một thanh ghi đơn giản (ví dụ v_a tại 8192) để kiểm tra sự tồn tại
            try:
                # read_registers trả về response object của pymodbus
                # Ở đây ta dùng read_serial_number() làm test nhanh
                sn = driver.read_serial_number()
                if sn:
                    logger.info(f"!!! FOUND Meter at Slave ID {slave_id}. Serial Number: {sn}")
                    data = driver.read_all()
                    if data:
                        print(json.dumps(data, indent=4))
                    found = True
                    # Nếu chỉ tìm 1 thiết bị thì có thể break ở đây
                    # break 
                else:
                    # Nếu SN trả về None hoặc lỗi, thử đọc v_a
                    resp = transport.read_holding_registers(8192, 2, slave=slave_id)
                    if not resp.isError():
                        logger.info(f"!!! FOUND device at Slave ID {slave_id} (Response OK, but SN null)")
                        data = driver.read_all()
                        if data:
                            print(json.dumps(data, indent=4))
                        found = True
            except Exception as e:
                continue
        
        if not found:
            logger.warning("Scan completed. No device found in the specified range.")
            
    finally:
        transport.close()
