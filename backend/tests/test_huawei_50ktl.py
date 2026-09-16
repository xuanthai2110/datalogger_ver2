import unittest
from unittest.mock import MagicMock

from backend.drivers.inverters.huawei_sun2000_50ktl import Huaweisun200050ktl, HuaweiSUN200050KTL


class TestHuaweiSUN200050KTL(unittest.TestCase):
    def setUp(self):
        self.mock_transport = MagicMock()
        self.driver = Huaweisun200050ktl(transport=self.mock_transport, slave_id=1)

    def test_class_aliases(self):
        self.assertIs(HuaweiSUN200050KTL, Huaweisun200050ktl)

    def test_register_map_structure(self):
        reg_map = self.driver.register_map()
        self.assertIn("info", reg_map)
        self.assertIn("ac", reg_map)
        self.assertIn("dc", reg_map)
        self.assertIn("string", reg_map)
        self.assertIn("stat", reg_map)
        self.assertIn("control", reg_map)

        # Check MPPT count (4 MPPTs)
        dc_regs = reg_map["dc"]
        mppt_voltages = [r for r in dc_regs if "voltage" in r["name"]]
        self.assertEqual(len(mppt_voltages), 4)

        # Check String count (8 strings)
        string_regs = reg_map["string"]
        self.assertEqual(len(string_regs), 8)
        self.assertEqual(string_regs[0]["name"], "string_1_current")
        self.assertEqual(string_regs[0]["address"], 32017)
        self.assertEqual(string_regs[7]["name"], "string_8_current")
        self.assertEqual(string_regs[7]["address"], 32031)

    def test_read_info_fallback(self):
        self.mock_transport.read_holding_registers.side_effect = Exception("Read failed")
        info = self.driver.read_info()

        self.assertEqual(info["brand"], "Huawei")
        self.assertEqual(info["model"], "SUN2000-50KTL")
        self.assertEqual(info["capacity_kw"], 50.0)
        self.assertEqual(info["mppt_count"], 4)
        self.assertEqual(info["string_count"], 8)
        self.assertFalse(info["is_active"])


if __name__ == "__main__":
    unittest.main()
