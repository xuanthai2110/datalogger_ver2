import sys
import logging
import time

sys.path.append(".")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CanadianUnlock")

from backend.communication.modbus_rtu import ModbusRTU

def test_address_config(transport, slave_id, mode_name, func_to_call, target_address):
    try:
        # Gọi hàm đọc động (Hàm 03 hoặc Hàm 04)
        res = func_to_call(address=target_address, count=1, slave=slave_id)
        
        if res is not None:
            # Kiểm tra lỗi Modbus Exception
            if (hasattr(res, 'isError') and res.isError()) or "ExceptionResponse" in type(res).__name__:
                return False, f"Modbus Code = {getattr(res, 'exception_code', 'Unknown')}"
            
            if hasattr(res, 'registers') and len(res.registers) > 0:
                return True, res.registers[0]
        return False, "Timeout (Không phản hồi)"
    except Exception as e:
        return False, str(e)

def main():
    # Cấu hình cố định cho USB1, baudrate 9600, 8N1
    port = "/dev/ttyUSB1"
    baudrate = 9600
    parity = "N"
    stopbits = 1
    bytesize = 8
    timeout = 0.5
    retries = 1

    # Địa chỉ Input Register muốn đọc Serial Number (Solis registers 3060‑3063)
    serial_address = 3060
    register_count = 4  # Đọc 4 thanh ghi chứa serial numberục đích) để nhận dữ liệu

    # Dải Slave ID cần quét (1‑8)
    slave_ids = range(1,9)


    transport = ModbusRTU(
        port=port,
        baudrate=baudrate,
        parity=parity,
        stopbits=stopbits,
        bytesize=bytesize,
        timeout=timeout,
        retries=retries,
    )

    if not transport.connect():
        logger.error(f"Không thể mở cổng {port}")
        return

    logger.info(f"Bắt đầu quét Slave IDs 1‑8 trên {port} (9600 8N1) – đọc Input Register 0x{serial_address:04X}")

    for slave_id in slave_ids:
        try:
            res = transport.read_input_registers(address=serial_address, count=register_count, slave=slave_id)
            if res is not None and not getattr(res, "isError", lambda: False)():
                regs = getattr(res, "registers", [])
                if len(regs) >= register_count:
                    # Chuyển các thanh ghi 16‑bit thành chuỗi ASCII (big‑endian)
                    byte_list = []
                    for reg in regs:
                        high = (reg >> 8) & 0xFF
                        low = reg & 0xFF
                        byte_list.extend([high, low])
                    try:
                        ascii_str = bytes(byte_list).decode("ascii", errors="ignore")
                    except Exception:
                        ascii_str = ""
                    print("\n" + "*" * 70)
                    logger.info("PHÁT HIỆN INVERTER VÀ ĐỌC DỮ LIỆU ASCII THÀNH CÔNG!")
                    print(f"   Slave ID       : {slave_id}")
                    print(f"   Raw registers  : {regs}")
                    print(f"   ASCII string   : '{ascii_str}'")
                    # Ghép serial number từ 4 thanh ghi (hex)
                    sn_hex = "".join(f"{reg:04X}" for reg in reversed(regs))
                    print(f"   Serial Number  : {sn_hex}")
                    print("*" * 70 + "\n")
                else:
                    logger.warning(f"Slave ID {slave_id}: Không đủ thanh ghi trả về")
            else:
                logger.warning(f"Slave ID {slave_id}: Không phản hồi hoặc lỗi Modbus")
        except Exception as e:
            logger.error(f"Slave ID {slave_id}: Lỗi ngoại lệ {e}")
        time.sleep(0.1)

    transport.close()
    logger.info("Quét hoàn tất.")

if __name__ == "__main__":
    main()