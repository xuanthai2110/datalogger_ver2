import sys
import logging
from unittest.mock import MagicMock

# Tránh lỗi UnicodeEncodeError trên Windows CMD/PowerShell khi in tiếng Việt
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Thêm đường dẫn dự án vào sys.path để import
sys.path.append(".")

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TestSolisMock")

from backend.drivers.inverters.solis_100k import Solis100k
from backend.drivers.inverters.solis_110k import Solis110k

def test_solis_driver(driver_class, model_name):
    logger.info(f"--- BẮT ĐẦU TEST MOCK CHO DRIVER SOLIS {model_name} ---")
    
    # Tạo transport giả lập
    mock_transport = MagicMock()
    
    # Định nghĩa dữ liệu giả lập cho 4 block
    # Block 1: 2999 - 3015 (17 registers)
    # Các giá trị giả lập:
    # 2999: model=123
    # 3000: dsp=207 (0x0207 -> "2.7")
    # 3001: lcd=101
    # 3004-3005: p_inv_w = 50000W (0x0000, 0xC350)
    # 3006-3007: p_dc_w = 51000W (0x0000, 0xC738)
    # 3008-3009: e_total = 123456kWh (0x0001, 0xE240)
    # 3014: e_daily = 450 (45.0kWh)
    mock_block1 = [0] * 17
    mock_block1[2999 - 2999] = 123
    mock_block1[3000 - 2999] = 207
    mock_block1[3001 - 2999] = 101
    mock_block1[3004 - 2999] = 0x0000
    mock_block1[3005 - 2999] = 0xC350
    mock_block1[3006 - 2999] = 0x0000
    mock_block1[3007 - 2999] = 0xC738
    mock_block1[3008 - 2999] = 0x0001
    mock_block1[3009 - 2999] = 0xE240
    mock_block1[3014 - 2999] = 450
    
    # Block 2: 3033 - 3091 (59 registers)
    # 3033-3035: U=220.5V (2205)
    # 3036-3038: I=75.6A (756)
    # 3041: temp=45.2C (452)
    # 3042: hz=50.02Hz (5002)
    # 3043: state=3 (Normal)
    # 3050: pf=0.995 (995)
    # 3055-3056: q_inv_var = 1000Var (0x0000, 0x03E8)
    # 3060-3063: sn_1=0x3412, sn_2=0x7856, sn_3=0xBC9A, sn_4=0xF0DE
    #            Khi đảo nibble & byte swap sẽ ra SN: "123456789ABCDEF0"
    # 3066-3070: fault 1-5 = 0
    # 3091: ir=1500kOhm
    mock_block2 = [0] * 59
    mock_block2[3033 - 3033] = 2205
    mock_block2[3034 - 3033] = 2205
    mock_block2[3035 - 3033] = 2205
    mock_block2[3036 - 3033] = 756
    mock_block2[3037 - 3033] = 756
    mock_block2[3038 - 3033] = 756
    mock_block2[3041 - 3033] = 452
    mock_block2[3042 - 3033] = 5002
    mock_block2[3043 - 3033] = 3
    mock_block2[3050 - 3033] = 995
    mock_block2[3055 - 3033] = 0x0000
    mock_block2[3056 - 3033] = 0x03E8
    mock_block2[3060 - 3033] = 0x3412
    mock_block2[3061 - 3033] = 0x7856
    mock_block2[3062 - 3033] = 0xBC9A
    mock_block2[3063 - 3033] = 0xF0DE
    mock_block2[3091 - 3033] = 1500

    # Block 3: 3300 - 3319 (20 registers)
    # Dòng string = 8.5A (85)
    mock_block3 = [85] * 20

    # Block 4: 3499 - 3538 (40 registers)
    # MPPT V=600.2V (6002), MPPT I=12.5A (125)
    # Voltages ở index 0-9 (địa chỉ 3499-3508)
    # Currents ở index 30-39 (địa chỉ 3529-3538)
    mock_block4 = [0] * 40
    for idx in range(10):
        mock_block4[3499 + idx - 3499] = 6002
        mock_block4[3529 + idx - 3499] = 125

    # Cấu hình mock transport trả về đúng block
    def side_effect(address, count, slave=None):
        if address == 2999 and count == 17:
            return MagicMock(registers=mock_block1, isError=lambda: False)
        elif address == 3033 and count == 59:
            return MagicMock(registers=mock_block2, isError=lambda: False)
        elif address == 3300 and count == 20:
            return MagicMock(registers=mock_block3, isError=lambda: False)
        elif address == 3499 and count == 40:
            return MagicMock(registers=mock_block4, isError=lambda: False)
        raise ValueError(f"Unexpected read call: addr={address}, count={count}")
        
    mock_transport.read_input_registers.side_effect = side_effect

    # Khởi tạo driver
    driver = driver_class(mock_transport, slave_id=1)
    
    # Gọi read_all
    data = driver.read_all()
    
    # Kiểm tra các trường dữ liệu quan trọng
    assert data["brand"] == "Solis", "Lỗi brand"
    assert data["model"] == model_name, f"Lỗi model: {data['model']}"
    assert data["serial_number"] == "21436587A9CBED0F", f"Lỗi đảo byte Serial Number: {data['serial_number']}"
    assert round(data["v_a"], 2) == 220.5, f"Lỗi scale v_a: {data['v_a']}"
    assert round(data["i_a"], 2) == 75.6, f"Lỗi scale i_a: {data['i_a']}"
    assert data["p_inv_w"] == 50000, f"Lỗi p_inv_w: {data['p_inv_w']}"
    assert data["p_dc_w"] == 51000, f"Lỗi p_dc_w: {data['p_dc_w']}"
    assert data["e_total"] == 123456, f"Lỗi e_total: {data['e_total']}"
    assert round(data["e_daily"], 2) == 45.0, f"Lỗi e_daily: {data['e_daily']}"
    assert round(data["temp_c"], 2) == 45.2, f"Lỗi temp_c: {data['temp_c']}"
    assert round(data["grid_hz"], 2) == 50.02, f"Lỗi grid_hz: {data['grid_hz']}"
    assert data["state_id"] == 3, f"Lỗi state_id: {data['state_id']}"
    assert round(data["pf"], 3) == 0.995, f"Lỗi pf: {data['pf']}"
    assert data["q_inv_var"] == 1000, f"Lỗi q_inv_var: {data['q_inv_var']}"
    assert data["ir"] == 1500, f"Lỗi ir: {data['ir']}"
    
    # Kiểm tra dòng các string
    for i in range(1, 21):
        assert round(data[f"string_{i}_current"], 2) == 8.5, f"Lỗi string_{i}_current: {data[f'string_{i}_current']}"
        
    # Kiểm tra MPPT
    for i in range(1, 11):
        assert round(data[f"mppt_{i}_voltage"], 2) == 600.2, f"Lỗi mppt_{i}_voltage: {data[f'mppt_{i}_voltage']}"
        assert round(data[f"mppt_{i}_current"], 2) == 12.5, f"Lỗi mppt_{i}_current: {data[f'mppt_{i}_current']}"

    logger.info(f"[SUCCESS] Driver Solis {model_name} vượt qua tất cả bài kiểm định Mock!")

def main():
    try:
        test_solis_driver(Solis100k, "100K")
        test_solis_driver(Solis110k, "110K")
        print("\n=============================================")
        print("TẤT CẢ UNIT TEST MOCK CHO SOLIS ĐÃ THÀNH CÔNG!")
        print("=============================================")
    except AssertionError as e:
        logger.error(f"[FAILED] Lỗi xác minh dữ liệu: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[CRITICAL] Lỗi không xác định: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
