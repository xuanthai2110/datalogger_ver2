"""
Script kiểm thử đọc dữ liệu từ Solis Hybrid Inverter S6-EH3P99.9K10-NV-YD-H
Hỗ trợ đọc 1 hoặc nhiều Inverter (Slave 1, Slave 2...) và tính toán tổng hợp khối `project` chuẩn xác.

Sử dụng:
1. Chạy với dữ liệu giả lập 2 Inverter (Offline Test):
   python test_S6-EH3P99.9K10-NV-YD-H.py --mock

2. Chạy đọc RS485 cổng COM thực tế cho 2 Inverter (Slave 1 & Slave 2):
   python test_S6-EH3P99.9K10-NV-YD-H.py --port COM3 --baud 9600 --slaves 1 2

3. Chạy đọc qua Modbus TCP (Ví dụ: IP 192.168.1.104, Slave 1 & Slave 2):
   python test_S6-EH3P99.9K10-NV-YD-H.py --host 192.168.1.104 --tcp-port 502 --slaves 1 2
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import TelemetryService & CacheDB từ backend
from backend.services.telemetry_service import TelemetryService
from backend.db_manager.cache import CacheDB


class InverterMeta:
    def __init__(self, inv_id: int, serial_number: str):
        self.id = inv_id
        self.serial_number = serial_number
        self.is_active = True


# Import Driver
try:
    from backend.drivers.inverters.solis_S6_EH3P99_9K10_NV_YD_H import SolisS6HybridDriver
except ImportError:
    from backend.drivers.solis_S6_EH3P99_9K10_NV_YD_H import SolisS6HybridDriver

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TestS6Hybrid")


class MockSolisTransport:
    """Mock Transport để test đọc dữ liệu offline hỗ trợ nhiều Slave ID."""

    def __init__(self):
        self.mock_registers_slave1 = {
            # 33004 ~ 33019: Serial Number ASCII "105322025C260025"
            33004: [0x3130, 0x3533, 0x3232, 0x3032, 0x3543, 0x3236, 0x3030, 0x3235, 0, 0, 0, 0, 0, 0, 0, 0],
            # 33073 ~ 33078: Va=221.0V, Vb=218.9V, Vc=223.2V, Ia=0.4A, Ib=0.6A, Ic=17.1A
            33073: [2210, 2189, 2232, 4, 6, 171],
            # 33079 ~ 33084: P_ac=5400W, Q_ac=-240VAr, S_ac=5410VA
            33079: [0, 5400, 0xFFFE, 0xFF10, 0, 5410],
            33094: [5013],
            33093: [317], # Temp=31.7C
            33029: [0, 2463], # E_total=2463 kWh
            33035: [620],     # E_daily=62.0 kWh
            33049: [7992, 7, 7924, 7, 7982, 7, 7940, 7, 0, 7600, 7937, 7, 7428, 8, 7389, 8, 7447, 8],
            34498: [7357, 7, 7370, 7],
            34903: [0, 7600],  # P_dc=7600W
            33251: [2244, 585, 2221, 880, 2255, 2627, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1123, 0, 0, 0, 0, 0, 0, 0, 3879, 0, 5012, 0, 14358, 0, 6593],
            33177: [0, 1494, 94],
            33147: [7300], 34343: [0],
            33137: [2215, 12], 33153: [2189, 16, 2237, 13], 34613: [0, 820],
            33133: [4290, 0, 0, 0, 0, 0, 100, 100],
            33149: [0, 0], 33041: [2000], 33161: [0, 988, 175, 0, 0, 668, 36], 33295: [4],
            34348: [3411, 3420, 223, 251], 43011: [15],
            34289: [4285, 0], 34277: [230, 98, 98, 4280, 2000, 2000], 34368: [0, 0], 34371: [150]
        }
        
        self.mock_registers_slave2 = {
            # 33004 ~ 33019: Serial Number ASCII "105322025C260026"
            33004: [0x3130, 0x3533, 0x3232, 0x3032, 0x3543, 0x3236, 0x3030, 0x3236, 0, 0, 0, 0, 0, 0, 0, 0],
            # 33073 ~ 33078: Va=220.5V, Vb=219.5V, Vc=222.8V, Ia=0.5A, Ib=0.8A, Ic=16.8A
            33073: [2205, 2195, 2228, 5, 8, 168],
            # 33079 ~ 33084: P_ac=4800W, Q_ac=-150VAr, S_ac=4810VA
            33079: [0, 4800, 0xFFFF, 0xFF6A, 0, 4810],
            33094: [5012],
            33093: [325], # Temp=32.5C
            33029: [0, 1850], # E_total=1850 kWh
            33035: [485],     # E_daily=48.5 kWh
            33049: [7800, 6, 7850, 6, 7900, 6, 7820, 6, 0, 6900, 7810, 6, 7300, 7, 7320, 7, 7350, 7],
            34498: [7310, 6, 7320, 6],
            34903: [0, 6900],  # P_dc=6900W
            33251: [2240, 500, 2220, 800, 2250, 2500, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0, 3500, 0, 5012, 0, 10000, 0, 5000],
            33177: [0, 1000, 50],
            33147: [5000], 34343: [0],
            33133: [4280, 0, 0, 0, 0, 0, 99, 99],
            33149: [0, 0], 33041: [2000], 33161: [0, 800, 150, 0, 0, 500, 30], 33295: [4],
            34348: [3410, 3418, 220, 248], 43011: [15],
            34289: [4275, 0], 34277: [225, 97, 97, 4270, 2000, 2000], 34368: [0, 0], 34371: [150]
        }

    def read_input_registers(self, address, count, slave=1):
        class Result:
            pass
        res = Result()
        regs_dict = self.mock_registers_slave2 if slave == 2 else self.mock_registers_slave1
        res.registers = regs_dict.get(address, [0] * count)
        if len(res.registers) < count:
            res.registers = (res.registers + [0] * count)[:count]
        res.isError = lambda: False
        return res

    def read_holding_registers(self, address, count, slave=1):
        class Result:
            pass
        res = Result()
        regs_dict = self.mock_registers_slave2 if slave == 2 else self.mock_registers_slave1
        res.registers = regs_dict.get(address, [0] * count)
        if len(res.registers) < count:
            res.registers = (res.registers + [0] * count)[:count]
        res.isError = lambda: False
        return res


def main():
    parser = argparse.ArgumentParser(description="Test Solis Hybrid S6 Multi-Inverter Telemetry V2 Build Payload")
    parser.add_argument("--mock", action="store_true", help="Chạy chế độ giả lập (Mock data test)")
    parser.add_argument("--port", type=str, default=None, help="Cổng COM nối RS485 (Ví dụ: COM3 hoặc /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600, help="Baudrate (Mặc định 9600)")
    parser.add_argument("--host", type=str, default=None, help="Địa chỉ IP nếu dùng Modbus TCP")
    parser.add_argument("--tcp-port", type=int, default=502, help="Cổng Modbus TCP (Mặc định 502)")
    parser.add_argument("--slaves", nargs="+", type=int, default=None, help="Danh sách Slave IDs (Ví dụ: --slaves 1 2)")
    parser.add_argument("--slave", type=int, default=None, help="Slave ID đơn lẻ (Ví dụ: --slave 1)")
    args = parser.parse_args()

    # Xử lý danh sách Slave IDs
    if args.slaves:
        slave_ids = args.slaves
    elif args.slave is not None:
        slave_ids = [args.slave]
    else:
        slave_ids = [1, 2] # Mặc định test 2 Inverter (Slave 1 và Slave 2)

    transport = None

    if args.mock or (not args.port and not args.host):
        logger.info(f">>> Đang chạy ở CHẾ ĐỘ GIẢ LẬP (MOCK TEST) cho {len(slave_ids)} Inverters (Slaves: {slave_ids}) <<<")
        transport = MockSolisTransport()

    elif args.host:
        logger.info(f"Connecting to Modbus TCP Host: {args.host}:{args.tcp_port} (Slaves: {slave_ids})")
        try:
            from pymodbus.client import ModbusTcpClient
            client = ModbusTcpClient(host=args.host, port=args.tcp_port, timeout=3)
            if client.connect():
                logger.info("Modbus TCP connected successfully!")
                transport = client
            else:
                logger.error("Failed to connect Modbus TCP!")
                return
        except Exception as e:
            logger.error(f"Modbus TCP Connection Error: {e}")
            return

    elif args.port:
        logger.info(f"Connecting to Modbus RTU Port: {args.port} (Baudrate: {args.baud}, Slaves: {slave_ids})")
        try:
            from pymodbus.client import ModbusSerialClient
            client = ModbusSerialClient(
                port=args.port,
                baudrate=args.baud,
                parity='N',
                stopbits=1,
                bytesize=8,
                timeout=2
            )
            if client.connect():
                logger.info("Modbus Serial connected successfully!")
                transport = client
            else:
                logger.error(f"Failed to connect Serial Port {args.port}!")
                return
        except Exception as e:
            logger.error(f"Modbus Serial Connection Error: {e}")
            return

    ts_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+07:00"

    db_path = f"temp_test_telemetry_{os.getpid()}.db"
    if os.path.exists(db_path):
        try: os.remove(db_path)
        except Exception: pass

    cache_db = CacheDB(db_path)
    inverters_meta = []

    # Đọc dữ liệu tuần tự từ từng Inverter (Slave ID)
    for slave_id in slave_ids:
        logger.info(f"--- Đang đọc dữ liệu Inverter Slave ID {slave_id} ---")
        driver = SolisS6HybridDriver(transport=transport, slave_id=slave_id)

        info = driver.read_info()
        logger.info(f"Inverter Info [Slave {slave_id}]: Model={info['model']}, SN={info['serial_number']}, Firmware={info['firmware_version']}")

        ac_data = driver.read_ac()
        dc_data = driver.read_dc()
        errors_data = driver.read_errors()

        # Tính E_monthly của từng Inverter
        e_monthly_calc = 0.0
        try:
            from backend.services.energy_service import EnergyService
            from backend.db_manager import RealtimeDB
            rt_db = RealtimeDB("realtime.db")
            energy_svc = EnergyService(rt_db)
            state = energy_svc.calculate(inverter_id=slave_id, current_e_total=ac_data.get("E_total", 0.0))
            e_monthly_calc = state.get("E_monthly", 0.0) or 0.0
        except Exception:
            e_monthly_calc = 0.0

        ac_data["E_monthly"] = round(e_monthly_calc, 2)

        # Lưu dữ liệu AC vào CacheDB
        ac_cache_data = {
            "ir": ac_data.get("IR"),
            "temp_c": ac_data.get("Temp_C"),
            "p_inv_w": ac_data.get("P_ac"),
            "q_inv_var": ac_data.get("Q_ac"),
            "v_a": ac_data.get("V_a"),
            "v_b": ac_data.get("V_b"),
            "v_c": ac_data.get("V_c"),
            "i_a": ac_data.get("I_a"),
            "i_b": ac_data.get("I_b"),
            "i_c": ac_data.get("I_c"),
            "pf": ac_data.get("PF"),
            "grid_hz": ac_data.get("H"),
            "e_daily": ac_data.get("E_daily"),
            "e_total": ac_data.get("E_total"),
            "e_monthly": ac_data.get("E_monthly", 0.0),
            "p_dc_w": dc_data.get("P_dc")
        }
        cache_db.upsert_inverter_ac(inverter_id=slave_id, project_id=1, data=ac_cache_data)

        # Lưu MPPT & Strings vào CacheDB
        for m in dc_data.get("mppts", []):
            m_idx = m["mppt_index"]
            cache_db.upsert_mppt(inverter_id=slave_id, mppt_index=m_idx, project_id=1, data={
                "v_mppt": m.get("V_mppt"),
                "i_mppt": m.get("I_mppt"),
                "p_mppt": m.get("P_mppt")
            })
            for s in m.get("strings", []):
                s_idx = s["string_index"]
                cache_db.upsert_string(inverter_id=slave_id, string_id=s_idx, project_id=1, mppt_id=m_idx, i_string=s.get("I_mppt", 0.0))

        # Lưu Lỗi vào CacheDB
        fault_json = json.dumps(errors_data)
        cache_db.upsert_error(
            inverter_id=slave_id,
            project_id=1,
            status_code=0,
            fault_code=errors_data[0].get("fault_code", 0) if errors_data else 0,
            status_text=errors_data[0].get("fault_description", "NORMAL") if errors_data else "NORMAL",
            fault_text=errors_data[0].get("fault_description", "NORMAL") if errors_data else "NORMAL",
            fault_json=fault_json
        )

        inverters_meta.append(InverterMeta(slave_id, info.get("serial_number", f"UNKNOWN_SN_{slave_id}")))

        # Đọc dữ liệu Grid Meter, Load và Battery từ Inverter
        grid_data = driver.read_grid_meter()
        if grid_data:
            cache_db.upsert_meter_cache(meter_id=1, project_id=1, data={
                "v_a": grid_data.get("u_a"),
                "v_b": grid_data.get("u_b"),
                "v_c": grid_data.get("u_c"),
                "i_a": grid_data.get("i_a"),
                "i_b": grid_data.get("i_b"),
                "i_c": grid_data.get("i_c"),
                "q_total": grid_data.get("q_grid_total"),
                "s_total": grid_data.get("s_grid_total"),
                "f": grid_data.get("f"),
                "e_pt_import": grid_data.get("e_import_total"),
                "e_pt_export": grid_data.get("e_export_total"),
            })

        load_data = driver.read_load()
        if load_data:
            cache_db.upsert_load_cache(project_id=1, data=load_data)

        batt_list = driver.read_battery()
        if batt_list:
            logger.info(f"Battery Data [Slave {slave_id}]: Đã đọc thành công {len(batt_list)} pack pin ({', '.join(b.get('serial_number','') for b in batt_list)})")
            cache_db.upsert_battery_cache(project_id=1, batteries=batt_list)
        else:
            logger.info(f"Battery Data [Slave {slave_id}]: Không phát hiện pack pin (No Battery)")

    # Dùng TelemetryService từ backend để xây dựng Telemetry V2 Payload chuẩn
    telemetry_svc = TelemetryService(realtime_db=None)
    payload_list = telemetry_svc.build_payload_from_cache(
        project_id=1,
        server_id=1,
        inverters_meta=inverters_meta,
        cache_db=cache_db
    )

    payload = payload_list[0] if payload_list else {}

    # In kết quả JSON Payload đầy đủ ra màn hình
    print("\n" + "=" * 80)
    print(f"=== HOÀN THÀNH BUILD TELEMETRY V2 PAYLOAD CHO {len(inverters_meta)} INVERTERS VỚI TELEMETRY SERVICE ===")
    print("=" * 80)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("=" * 80 + "\n")

    # Đóng kết nối & dọn dẹp file DB tạm
    if hasattr(transport, "close"):
        transport.close()
    try:
        if os.path.exists(db_path): os.remove(db_path)
    except Exception:
        pass


if __name__ == "__main__":
    main()
