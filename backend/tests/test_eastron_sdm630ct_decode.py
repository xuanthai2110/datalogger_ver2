import os
import sys
import unittest
import struct
from unittest.mock import MagicMock

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.drivers.eastron_sdm630ct import MeterEastronsdm630ct


class TestEastronSDM630CTDecode(unittest.TestCase):
    def setUp(self):
        self.transport = MagicMock()
        self.driver = MeterEastronsdm630ct(self.transport, slave_id=1)

    def float_to_registers(self, value: float):
        """Chuyển đổi một số float32 sang 2 thanh ghi 16-bit (Big-endian)."""
        raw = struct.pack(">f", value)
        return list(struct.unpack(">HH", raw))

    def test_read_all_decodes_correctly(self):
        # Thiết lập dữ liệu giả định
        expected_values = {
            0x0000: 220.1,  # v_a
            0x0002: 220.2,  # v_b
            0x0004: 220.3,  # v_c
            0x002A: 220.2,  # v_phase_avg
            0x0006: 5.1,    # i_a
            0x0008: 5.2,    # i_b
            0x000A: 5.3,    # i_c
            0x002E: 5.2,    # i_avg
            0x000C: 1100.0, # p_a
            0x000E: 1120.0, # p_b
            0x0010: 1130.0, # p_c
            0x0034: 3350.0, # p_total
            0x0018: 100.0,  # q_a
            0x001A: 110.0,  # q_b
            0x001C: 120.0,  # q_c
            0x003C: 330.0,  # q_total
            0x0012: 1105.0, # s_a
            0x0014: 1125.0, # s_b
            0x0016: 1136.0, # s_c
            0x0038: 3366.0, # s_total
            0x001E: 0.99,   # pf_a
            0x0020: 0.98,   # pf_b
            0x0022: 0.97,   # pf_c
            0x003E: 0.98,   # pf
            0x0046: 50.01,  # f
            0x00C8: 381.1,  # v_ab
            0x00CA: 381.2,  # v_bc
            0x00CC: 381.3,  # v_ca
            0x00CE: 381.2,  # v_line_avg
            0x0048: 12345.67,  # e_pt_import
            0x004A: 54321.12,  # e_pt_export
            0x004C: 123.45,    # e_qt_import
            0x004E: 543.21,    # e_qt_export
            0x0050: 12469.12,  # e_st_import
        }

        def mock_read_input_registers(address, count, slave=1):
            mock_resp = MagicMock()
            mock_resp.isError.return_value = False
            
            if address in expected_values:
                val = expected_values[address]
                mock_resp.registers = self.float_to_registers(val)
            else:
                mock_resp.registers = [0] * count
            return mock_resp

        self.transport.read_input_registers = mock_read_input_registers

        data = self.driver.read_all()
        self.assertIsNotNone(data)

        # Kiểm tra giải mã các trường quan trọng
        self.assertAlmostEqual(data["v_a"], 220.1)
        self.assertAlmostEqual(data["v_b"], 220.2)
        self.assertAlmostEqual(data["v_c"], 220.3)
        self.assertAlmostEqual(data["v_phase_avg"], 220.2)
        self.assertAlmostEqual(data["i_a"], 5.1)
        self.assertAlmostEqual(data["i_b"], 5.2)
        self.assertAlmostEqual(data["i_c"], 5.3)
        self.assertAlmostEqual(data["i_avg"], 5.2)
        self.assertAlmostEqual(data["p_a"], 1100.0)
        self.assertAlmostEqual(data["p_total"], 3350.0)
        self.assertAlmostEqual(data["q_total"], 330.0)
        self.assertAlmostEqual(data["s_total"], 3366.0)
        self.assertAlmostEqual(data["pf"], 0.98)
        self.assertAlmostEqual(data["f"], 50.01)
        self.assertAlmostEqual(data["v_ab"], 381.1)
        self.assertAlmostEqual(data["v_line_avg"], 381.2)
        self.assertAlmostEqual(data["e_pt_import"], 12345.67, places=2)
        self.assertAlmostEqual(data["e_pt_export"], 54321.12, places=2)
        self.assertAlmostEqual(data["e_qt_import"], 123.45, places=2)
        self.assertAlmostEqual(data["e_qt_export"], 543.21, places=2)
        self.assertAlmostEqual(data["e_st_import"], 12469.12, places=2)

    def test_read_serial_number(self):
        # Serial number: 3010024528
        # Hex: 0xB3695450 -> registers: [0xB369, 0x5450] = [45929, 21584]
        mock_resp = MagicMock()
        mock_resp.isError.return_value = False
        mock_resp.registers = [45929, 21584]

        self.transport.read_holding_registers = MagicMock(return_value=mock_resp)

        serial = self.driver.read_serial_number()
        self.assertEqual(serial, "3010024528")
        
        # Verify Holding Register (FC03) was called on address 0xFC00
        self.transport.read_holding_registers.assert_called_with(0xFC00, 2, slave=1)


if __name__ == "__main__":
    unittest.main()
