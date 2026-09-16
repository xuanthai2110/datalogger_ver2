import os
import sys
import json
import logging

# Thiet lap duong dan he thong de import cac module tu thu muc goc
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.communication.modbus_tcp import ModbusTCP
from backend.drivers.meters.chint_dtsu666 import MeterChintdtsu666

# Cau hinh logging (An cac thong bao warning/info he thong de console sach se)
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")


def try_raw_read(transport, fc: int, address: int, count: int, slave_id: int):
    """Doc thu register bang FC03 hoac FC04 de kiem tra thiet bi."""
    try:
        if fc == 3:
            response = transport.read_holding_registers(address, count, slave=slave_id)
        elif fc == 4:
            response = transport.read_input_registers(address, count, slave=slave_id)
        else:
            return False, "Function Code khong hop le"

        if response.isError():
            return False, f"Error: {response}"
        return True, response.registers
    except Exception as e:
        return False, str(e)


def run_auto_diagnosis(transport, target_slave_id: int):
    """Tu dong chan doan loi khi cau hinh mac dinh khong chay."""
    print("\n" + "="*50)
    print("      BAT DAU CHE DO TU DONG CHAN DOAN LOI MODBUS ")
    print("="*50)
    
    # 1. Thu nghiem FC04 (Read Input Registers) voi Slave ID mac dinh
    print(f"\n1. Thu nghiem doc voi Slave ID = {target_slave_id} qua FC04 (Input Registers)...")
    success, res = try_raw_read(transport, 4, 8198, 2, target_slave_id) # Dia chi v_a
    if success:
        print(f"   => THANH CONG! Thiet bi phan hoi qua FC04. Data: {res}")
        print(f"   => HUONG GIAI QUYET: Ban hay sua 'read_function = \"input\"' trong file backend/drivers/chint_dtsu666.py")
        return
    else:
        print(f"   => That bai voi FC04. Chi tiet: {res}")

    # 2. Quet cac Slave ID tu 1 den 15
    print("\n2. Quet cac Slave ID tu 1 den 15 (Kiem tra dia chi v_a 8198)...")
    found_any = False
    
    for sid in range(1, 16):
        # Thu FC03
        success_fc3, res_fc3 = try_raw_read(transport, 3, 8198, 2, sid)
        if success_fc3:
            print(f"   ===> PHAT HIEN THIET BI: Slave ID = {sid} phan hoi qua FC03 (Holding)! Data: {res_fc3}")
            found_any = True
            break
            
        # Thu FC04
        success_fc4, res_fc4 = try_raw_read(transport, 4, 8198, 2, sid)
        if success_fc4:
            print(f"   ===> PHAT HIEN THIET BI: Slave ID = {sid} phan hoi qua FC04 (Input)! Data: {res_fc4}")
            print(f"   => HUONG GIAI QUYET: Doi Slave ID thanh {sid} va set 'read_function = \"input\"' trong driver.")
            found_any = True
            break

    # 3. Thu quet them dia chi v_ab 8192 (neu quet 8198 khong ra thiet bi nao)
    if not found_any:
        print("\n3. Quet tiep dia chi v_ab 8192 tu 1 den 15...")
        for sid in range(1, 16):
            success_fc3, res_fc3 = try_raw_read(transport, 3, 8192, 2, sid)
            if success_fc3:
                print(f"   ===> PHAT HIEN THIET BI: Slave ID = {sid} phan hoi qua FC03 (Holding)! Data: {res_fc3}")
                found_any = True
                break
            success_fc4, res_fc4 = try_raw_read(transport, 4, 8192, 2, sid)
            if success_fc4:
                print(f"   ===> PHAT HIEN THIET BI: Slave ID = {sid} phan hoi qua FC04 (Input)! Data: {res_fc4}")
                found_any = True
                break

    if not found_any:
        print("\n[CANH BAO] Khong phat hien bat ky thiet bi nao phan hoi tu Slave ID 1 den 15.")
        print("Vui long kiem tra lai:")
        print("1. Day cap RS485 tu Gateway den Meter Chint DTSU666 co bi dau nguoc (A/B) hay khong.")
        print("2. Lamp Modbus tren Gateway co nhap nhay khi goi lenh doc khong.")
        print("3. Thiet bi do co dang bat nguon va Slave ID thuc su duoc thiet lap la bao nhieu.")
        
    print("="*50 + "\n")


def test_chint_dtsu666():
    ip_address = "192.168.0.10"
    port = 502
    slave_id = 7

    print(f"=== DANG KET NOI MODBUS TCP: {ip_address}:{port} (Slave ID: {slave_id}) ===")
    
    transport = ModbusTCP(
        host=ip_address,
        port=port,
        timeout=3.0,
        retries=3,
    )

    if not transport.connect():
        print(f"LOI: Khong the ket noi den {ip_address}:{port}")
        return

    try:
        # Khoi tao driver voi cau hinh hien tai
        meter = MeterChintdtsu666(transport, slave_id=slave_id)
        
        print("=== BAT DAU DOC THU DU LIEU (FC03, Slave 7) ===")
        data = meter.read_all()
        
        if data is None:
            print("LOI: Doc mac dinh that bai! Kich hoat che do tu dong chan doan...")
            run_auto_diagnosis(transport, slave_id)
        else:
            print("\n=== KET QUA DOC DU LIEU THANH CONG ===")
            print(json.dumps(data, indent=4, ensure_ascii=False))
            
            print("\n=== THONG SO CHI TIET ===")
            for key, val in data.items():
                reg_info = meter.register_map.get(key, {})
                unit = reg_info.get("unit", "")
                print(f"- {key:<15}: {val} {unit}")
                
    except Exception as e:
        print(f"Ngoai le xay ra khi doc: {e}")
        print("Kich hoat che do tu dong chan doan...")
        run_auto_diagnosis(transport, slave_id)
    finally:
        transport.close()
        print("=== DA DONG KET NOI ===")


if __name__ == "__main__":
    test_chint_dtsu666()
