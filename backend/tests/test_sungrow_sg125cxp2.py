import unittest
from unittest.mock import MagicMock

from backend.drivers.inverters.sungrow_sg125cxp2 import Sungrowsg125cxp2, SungrowSG125CXP2


class TestSungrowSG125CXP2(unittest.TestCase):
    def setUp(self):
        self.mock_transport = MagicMock()
        self.driver = Sungrowsg125cxp2(transport=self.mock_transport, slave_id=1)

    def test_class_aliases(self):
        self.assertIs(SungrowSG125CXP2, Sungrowsg125cxp2)

    def test_register_map_structure(self):
        reg_map = self.driver.register_map()
        self.assertIn("info", reg_map)
        self.assertIn("ac", reg_map)
        self.assertIn("dc", reg_map)
        self.assertIn("string", reg_map)
        self.assertIn("stat", reg_map)
        self.assertIn("control", reg_map)

        # Check MPPT count (12 MPPTs = 24 entries for v_mppt and i_mppt)
        dc_regs = reg_map["dc"]
        mppt_voltages = [r for r in dc_regs if "voltage" in r["name"]]
        mppt_currents = [r for r in dc_regs if "current" in r["name"]]
        self.assertEqual(len(mppt_voltages), 12)
        self.assertEqual(len(mppt_currents), 12)

        # Check String count (24 strings)
        string_regs = reg_map["string"]
        self.assertEqual(len(string_regs), 24)
        self.assertEqual(string_regs[0]["name"], "string_1_current")
        self.assertEqual(string_regs[0]["address"], 7012)
        self.assertEqual(string_regs[23]["name"], "string_24_current")
        self.assertEqual(string_regs[23]["address"], 7035)

    def test_read_info_fallback(self):
        # When transport fails, read_info fallback should return standard SG125CX-P2 specs
        self.mock_transport.read_input_registers.side_effect = Exception("Read failed")
        info = self.driver.read_info()

        self.assertEqual(info["brand"], "Sungrow")
        self.assertEqual(info["model"], "SG125CX-P2")
        self.assertEqual(info["capacity_kw"], 125.0)
        self.assertEqual(info["mppt_count"], 12)
        self.assertEqual(info["string_count"], 24)
        self.assertFalse(info["is_active"])

    def test_read_info_success(self):
        # Mock success reading info registers (address 4989..5000)
        # 10 regs serial_number + 1 reg type_code + 1 reg rated_power
        mock_response = MagicMock()
        mock_response.isError.return_value = False
        # Serial number "SG125TEST12", type_code 0x2C2D (11309), rated_power 1250 (125.0 kW)
        sn_bytes = b"SG125TEST12\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        sn_regs = [(sn_bytes[i] << 8) | sn_bytes[i+1] for i in range(0, 20, 2)]
        mock_response.registers = sn_regs + [0x2C2D, 1250]
        
        self.mock_transport.read_input_registers.return_value = mock_response

        info = self.driver.read_info()
        self.assertEqual(info["brand"], "Sungrow")
        self.assertEqual(info["model"], "SG125CX-P2")
        self.assertEqual(info["capacity_kw"], 125.0)
        self.assertEqual(info["type_code"], 0x2C2D)
        self.assertTrue(info["is_active"])


if __name__ == "__main__":
    unittest.main()
