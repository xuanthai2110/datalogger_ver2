import os
import sys
import unittest
from unittest.mock import MagicMock

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.drivers.meters.acrel_dtsd1352 import MeterAcreldtsd1352


class TestAcrelDTSD1352Decode(unittest.TestCase):
    def setUp(self):
        self.transport = MagicMock()
        self.driver = MeterAcreldtsd1352(self.transport, slave_id=1)

    def test_read_all_decodes_correctly(self):
        # Thiết lập mock phản hồi cho từng lần đọc registers
        # Chú ý: read_all duyệt qua register_map, gọi read_holding_registers cho từng field
        
        def mock_read_holding_registers(address, count, slave=1):
            mock_resp = MagicMock()
            mock_resp.isError.return_value = False

            if address == 0x0061:  # v_a
                mock_resp.registers = [2201]  # 220.1 V
            elif address == 0x0062:  # v_b
                mock_resp.registers = [2202]  # 220.2 V
            elif address == 0x0063:  # v_c
                mock_resp.registers = [2203]  # 220.3 V
            elif address == 0x0064:  # i_a
                mock_resp.registers = [199]   # 1.99 A
            elif address == 0x0065:  # i_b
                mock_resp.registers = [200]   # 2.00 A
            elif address == 0x0066:  # i_c
                mock_resp.registers = [201]   # 2.01 A
            elif address == 0x0077:  # f
                mock_resp.registers = [4998]  # 49.98 Hz
            elif address == 0x0078:  # v_ab
                mock_resp.registers = [3811]  # 381.1 V
            elif address == 0x0079:  # v_bc
                mock_resp.registers = [3812]  # 381.2 V
            elif address == 0x007A:  # v_ca
                mock_resp.registers = [3813]  # 381.3 V
            elif address == 0x0164:  # p_a
                mock_resp.registers = [0, 500] # 500 W
            elif address == 0x0166:  # p_b
                mock_resp.registers = [0, 500] # 500 W
            elif address == 0x0168:  # p_c
                mock_resp.registers = [0, 500] # 500 W
            elif address == 0x016A:  # p_total
                mock_resp.registers = [0, 1500] # 1500 W
            elif address == 0x016C:  # q_a
                mock_resp.registers = [0, 100]  # 100 Var
            elif address == 0x016E:  # q_b
                mock_resp.registers = [0, 100]  # 100 Var
            elif address == 0x0170:  # q_c
                mock_resp.registers = [0, 100]  # 100 Var
            elif address == 0x0172:  # q_total
                mock_resp.registers = [0, 300]  # 300 Var
            elif address == 0x0174:  # s_a
                mock_resp.registers = [0, 510]  # 510 VA
            elif address == 0x0176:  # s_b
                mock_resp.registers = [0, 510]  # 510 VA
            elif address == 0x0178:  # s_c
                mock_resp.registers = [0, 510]  # 510 VA
            elif address == 0x017A:  # s_total
                mock_resp.registers = [0, 1530] # 1530 VA
            elif address == 0x017C:  # pf_a
                mock_resp.registers = [980]   # 0.980
            elif address == 0x017D:  # pf_b
                mock_resp.registers = [981]   # 0.981
            elif address == 0x017E:  # pf_c
                mock_resp.registers = [982]   # 0.982
            elif address == 0x017F:  # pf
                mock_resp.registers = [980]   # 0.980
            elif address == 0x000A:  # e_pt_import
                # 123456 = 0x0001E240 -> [0x0001, 0xE240] = [1, 57920]
                mock_resp.registers = [1, 57920] # 1234.56 kWh
            elif address == 0x0014:  # e_pt_export
                mock_resp.registers = [0, 50000] # 500.00 kWh
            elif address == 0x0028:  # e_qt_import
                mock_resp.registers = [0, 20000] # 200.00 kVarh
            elif address == 0x0032:  # e_qt_export
                mock_resp.registers = [0, 10000] # 100.00 kVarh
            else:
                mock_resp.registers = [0] * count

            return mock_resp

        self.transport.read_holding_registers = mock_read_holding_registers

        data = self.driver.read_all()
        self.assertIsNotNone(data)

        # Kiểm tra giải mã điện áp, dòng điện, tần số
        self.assertAlmostEqual(data["v_a"], 220.1)
        self.assertAlmostEqual(data["v_b"], 220.2)
        self.assertAlmostEqual(data["v_c"], 220.3)
        self.assertAlmostEqual(data["i_a"], 1.99)
        self.assertAlmostEqual(data["i_b"], 2.00)
        self.assertAlmostEqual(data["i_c"], 2.01)
        self.assertAlmostEqual(data["f"], 49.98)

        # Kiểm tra điện áp dây
        self.assertAlmostEqual(data["v_ab"], 381.1)
        self.assertAlmostEqual(data["v_bc"], 381.2)
        self.assertAlmostEqual(data["v_ca"], 381.3)

        # Kiểm tra công suất
        self.assertAlmostEqual(data["p_a"], 500.0)
        self.assertAlmostEqual(data["p_total"], 1500.0)
        self.assertAlmostEqual(data["q_total"], 300.0)
        self.assertAlmostEqual(data["s_total"], 1530.0)

        # Kiểm tra hệ số công suất
        self.assertAlmostEqual(data["pf"], 0.980)

        # Kiểm tra năng lượng tích lũy
        self.assertAlmostEqual(data["e_pt_import"], 1234.56)
        self.assertAlmostEqual(data["e_pt_export"], 500.0)
        self.assertAlmostEqual(data["e_qt_import"], 200.0)
        self.assertAlmostEqual(data["e_qt_export"], 100.0)


if __name__ == "__main__":
    unittest.main()
