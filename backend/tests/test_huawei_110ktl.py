import sys
import os
import logging
import json
from datetime import datetime

# Thêm thư mục gốc vào PYTHONPATH để có thể import các module trong backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.communication.modbus_tcp import ModbusTCP
from backend.drivers.inverters.huawei_sun2000_110ktl import Huaweisun2000110ktl

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestHuawei")

def build_payload(raw_data):
    """
    Hàm mô phỏng TelemetryService.build_payload_from_cache
    để xây dựng payload chuẩn giống như cấu trúc gửi lên server.
    """
    now = datetime.now()
    payload_created_at = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+07:00"

    # 1. Thu thập dữ liệu AC
    ac_payload = {
        "IR": round(float(raw_data.get("ir", 0)), 2),
        "Temp_C": round(float(raw_data.get("temp_c", 0)), 2),
        "P_ac": round(float(raw_data.get("p_inv_w", 0)) / 1000.0, 2), # Chuyển Watt sang kW
        "Q_ac": round(float(raw_data.get("q_inv_var", 0)) / 1000.0, 2), # Chuyển Var sang kVar
        "V_a": round(float(raw_data.get("v_a", 0)), 2),
        "V_b": round(float(raw_data.get("v_b", 0)), 2),
        "V_c": round(float(raw_data.get("v_c", 0)), 2),
        "I_a": round(float(raw_data.get("i_a", 0)), 2),
        "I_b": round(float(raw_data.get("i_b", 0)), 2),
        "I_c": round(float(raw_data.get("i_c", 0)), 2),
        "PF": round(float(raw_data.get("pf", 1.0)), 2),
        "H": round(float(raw_data.get("grid_hz", 50.0)), 2),
        "E_daily": round(float(raw_data.get("e_daily", 0)), 2),
        "E_monthly": round(float(raw_data.get("e_daily", 0)), 2), # Fallback monthly to daily if not defined
        "E_total": round(float(raw_data.get("e_total", 0)), 2),
        "created_at": payload_created_at
    }

    # 2. Thu thập dữ liệu MPPT và String
    mppt_list = []
    total_p_dc = 0.0
    
    for i in range(1, 11):
        v_mppt = float(raw_data.get(f"mppt_{i}_voltage", 0))
        i_mppt = float(raw_data.get(f"mppt_{i}_current", 0))
        p_mppt = round(v_mppt * i_mppt, 2)
        total_p_dc += p_mppt
        
        # Lấy danh sách string thuộc MPPT này (mỗi MPPT có 2 string)
        string_list = []
        for s_idx in [2 * i - 1, 2 * i]:
            string_list.append({
                "string_index": s_idx,
                "I_mppt": round(float(raw_data.get(f"string_{s_idx}_current", 0)), 2),
                "Max_I": 15.0, # Giá trị mặc định hoặc thiết lập từ datasheet
                "created_at": payload_created_at
            })

        mppt_list.append({
            "mppt_index": i,
            "string_on_mppt": 2,
            "V_mppt": round(v_mppt, 2),
            "I_mppt": round(i_mppt, 2),
            "P_mppt": round(p_mppt / 1000.0, 2), # kW
            "Max_I": 30.0,
            "Max_V": 1100.0,
            "Max_P": 15.0,
            "created_at": payload_created_at,
            "strings": string_list
        })
    
    # 3. Thu thập mã lỗi / Trạng thái hoạt động
    # Huawei SUN2000: state_id (32089) và fault_code (32090)
    state_id = raw_data.get("state_id", 0)
    fault_code = raw_data.get("fault_code", 0)
    
    severity = "STABLE"
    status_text = "STANDBY"
    if state_id == 0x0200 or state_id == 0x0201 or state_id == 0x0202:
        status_text = "ON-GRID"
    elif state_id == 0x0300:
        status_text = "FAULT"
        severity = "ERROR"
    elif state_id == 0x0000 or state_id == 0x0001 or state_id == 0x0002 or state_id == 0x0003:
        status_text = "STANDBY"
        
    if fault_code > 0:
        severity = "ERROR"
        status_text = "FAULT"

    errors = [{
        "fault_code": fault_code,
        "fault_description": f"Huawei Status: {status_text} (State ID: {state_id}, Fault Code: {fault_code})",
        "repair_instruction": "Check inverter manual for fault code." if fault_code > 0 else "",
        "severity": severity,
        "created_at": payload_created_at
    }]

    # 4. Gom thành thông tin Inverter
    inverter_data = {
        "serial_number": raw_data.get("serial_number", "TEST_SERIAL"),
        "ac": ac_payload,
        "mppts": mppt_list,
        "errors": errors
    }

    # 5. Tổng hợp dữ liệu Project
    project_payload = {
        "Temp_C": ac_payload["Temp_C"],
        "P_ac": ac_payload["P_ac"],
        "P_dc": round(total_p_dc / 1000.0, 2), # kW
        "E_daily": ac_payload["E_daily"],
        "E_monthly": ac_payload["E_monthly"],
        "E_total": ac_payload["E_total"],
        "severity": severity,
        "created_at": payload_created_at
    }

    # Payload gửi lên API Server
    return {
        "project": project_payload,
        "inverters": [inverter_data]
    }

def main():
    HOST = "192.168.0.10"
    PORT = 502
    SLAVE_ID = 1

    logger.info(f"--- Đang kết nối tới Inverter Huawei qua Modbus TCP: {HOST}:{PORT}, Slave ID: {SLAVE_ID} ---")
    transport = ModbusTCP(host=HOST, port=PORT, timeout=5, retries=2)
    
    if not transport.connect():
        logger.error("Kết nối Modbus TCP thất bại!")
        return

    try:
        driver = Huaweisun2000110ktl(transport, slave_id=SLAVE_ID)
        
        logger.info("Đang đọc dữ liệu thời gian thực từ Inverter...")
        raw_data = driver.read_all()
        
        if not raw_data:
            logger.error("Không đọc được dữ liệu từ Inverter!")
            return

        logger.info("Đọc dữ liệu thành công! Đang tiến hành đóng gói payload...")
        payload = build_payload(raw_data)
        
        logger.info("--- PAYLOAD TELEMETRY ĐÃ ĐÓNG GÓI ---")
        print(json.dumps(payload, indent=4, ensure_ascii=False))

    except Exception as e:
        logger.error(f"Có lỗi xảy ra khi test: {e}", exc_info=True)
    finally:
        transport.close()

if __name__ == "__main__":
    main()
