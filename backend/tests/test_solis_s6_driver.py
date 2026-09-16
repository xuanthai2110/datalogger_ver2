import unittest
from unittest.mock import MagicMock
from backend.drivers.inverters.solis_S6_EH3P99_9K10_NV_YD_H import SolisS6HybridDriver


class MockModbusResponse:
    def __init__(self, registers):
        self.registers = registers

    def isError(self):
        return False


class TestSolisS6HybridDriver(unittest.TestCase):
    def setUp(self):
        self.transport = MagicMock()
        self.driver = SolisS6HybridDriver(transport=self.transport, slave_id=1)

    def test_register_map(self):
        reg_map = self.driver.register_map()
        self.assertIn("info", reg_map)
        self.assertIn("ac", reg_map)
        self.assertIn("dc", reg_map)
        self.assertIn("grid", reg_map)
        self.assertIn("load", reg_map)
        self.assertIn("battery", reg_map)
        self.assertIn("errors", reg_map)

    def test_read_info(self):
        # 16 registers for SN, 1 register for DSP ver
        sn_regs = [0x3132, 0x3042, 0x3232, 0x3031, 0x3031, 0x3030, 0x3100, 0x0000,
                   0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000]
        dsp_regs = [0x001A]

        def mock_read_input(address, count, slave=1):
            if address == 33004:
                return MockModbusResponse(sn_regs)
            elif address == 33001:
                return MockModbusResponse(dsp_regs)
            return MockModbusResponse([0] * count)

        self.transport.read_input_registers.side_effect = mock_read_input
        info = self.driver.read_info()
        self.assertEqual(info["brand"], "Solis")
        self.assertEqual(info["model"], "S6-EH3P99.9K10-NV-YD-H")
        self.assertEqual(info["mppt_count"], 10)
        self.assertEqual(info["string_count"], 20)

    def test_read_dc_10_mppts(self):
        # Mock raw_pv1_8 (33049 ~ 33066, 18 registers)
        # MPPT 1: V=6000 (600V), I=150 (15A)
        # MPPT 2: V=6100 (610V), I=160 (16A)
        # MPPT 3: V=6200, I=170
        # MPPT 4: V=6300, I=180
        # Total PV Power: 33057~33058 = 100000 (100kW)
        # MPPT 5: V=6400, I=190
        # MPPT 6: V=6500, I=200
        # MPPT 7: V=6600, I=210
        # MPPT 8: V=6700, I=220
        raw_pv1_8 = [
            6000, 150, 6100, 160, 6200, 170, 6300, 180,  # 0..7
            0x0001, 0x86A0,                             # 8..9 (Total PV Power = 100kW)
            6400, 190, 6500, 200, 6600, 210, 6700, 220   # 10..17
        ]
        # MPPT 9..10 (34498 ~ 34501)
        raw_pv9_10 = [
            6800, 230, 6900, 240
        ]

        def mock_read_input(address, count, slave=1):
            if address == 33049:
                return MockModbusResponse(raw_pv1_8)
            elif address == 34498:
                return MockModbusResponse(raw_pv9_10)
            elif address == 34903:
                return MockModbusResponse([0x0001, 0x86A0])
            return MockModbusResponse([0] * count)

        self.transport.read_input_registers.side_effect = mock_read_input
        dc = self.driver.read_dc()

        self.assertIn("mppts", dc)
        self.assertEqual(len(dc["mppts"]), 10)
        self.assertEqual(dc["mppts"][0]["V_mppt"], 600.0)
        self.assertEqual(dc["mppts"][0]["I_mppt"], 15.0)
        self.assertEqual(len(dc["mppts"][0]["strings"]), 2)
        self.assertEqual(dc["mppts"][4]["V_mppt"], 640.0) # MPPT 5
        self.assertEqual(dc["mppts"][8]["V_mppt"], 680.0) # MPPT 9
        self.assertEqual(dc["mppts"][9]["V_mppt"], 690.0) # MPPT 10

    def test_read_grid_meter(self):
        # 33251~33286 (36 registers)
        raw_meter = [0] * 36
        raw_meter[0] = 2300 # Ua = 230V
        raw_meter[1] = 1000 # Ia = 10A (0.01A scale)
        raw_meter[2] = 2300 # Ub
        raw_meter[3] = 1000 # Ib
        raw_meter[4] = 2300 # Uc
        raw_meter[5] = 1000 # Ic
        # p_grid_total (offset 12) = 5000W
        raw_meter[12] = 0
        raw_meter[13] = 5000
        # pf (offset 30) = 99 (0.99)
        raw_meter[30] = 99
        # f (offset 31) = 5000 (50Hz)
        raw_meter[31] = 5000

        self.transport.read_input_registers.return_value = MockModbusResponse(raw_meter)
        grid = self.driver.read_grid_meter()
        self.assertEqual(grid["u_a"], 230.0)
        self.assertEqual(grid["i_a"], 10.0)
        self.assertEqual(grid["p_grid_total"], 5000.0)
        self.assertEqual(grid["pf"], 0.99)
        self.assertEqual(grid["f"], 50.0)

    def test_read_battery(self):
        # 33133~33140 (8 regs)
        raw_b1 = [5200, 100, 0, 0, 0, 0, 85, 99] # U=520V, I=10A, SOC=85%, SOH=99%
        def mock_read_input(address, count, slave=1):
            if address == 33133:
                return MockModbusResponse(raw_b1)
            return MockModbusResponse([0] * count)
        self.transport.read_input_registers.side_effect = mock_read_input
        batt = self.driver.read_battery()
        self.assertIsNotNone(batt)
        self.assertEqual(len(batt), 1)
        self.assertEqual(batt[0]["inv_batt_u"], 520.0)
        self.assertEqual(batt[0]["inv_batt_i"], 10.0)
        self.assertEqual(batt[0]["bms_batt_soc"], 85)
        self.assertTrue(batt[0]["serial_number"].startswith("BATT_"))

    def test_power_limit_control(self):
        self.transport.write_register.return_value = MockModbusResponse([])
        res1 = self.driver.enable_power_limit(True)
        self.assertTrue(res1)
        self.transport.write_register.assert_called_with(43132, 2, slave=1)

        res2 = self.driver.write_power_limit_kw(50.0)
        self.assertTrue(res2)
        self.transport.write_register.assert_called_with(43128, 5000, slave=1)


if __name__ == "__main__":
    unittest.main()
