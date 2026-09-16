import unittest
import tempfile
import os
from unittest.mock import MagicMock

from backend.db_manager import MetadataDB, RealtimeDB
from backend.services.project_service import ProjectService
from backend.services.setup_service import SetupService
from backend.models.project import ProjectCreate
from backend.drivers.batteries.pylontech_bms import PylontechBMSDriver

class TestBatteryDriverScan(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.rt_fd, self.rt_path = tempfile.mkstemp()
        self.meta_db = MetadataDB(self.db_path)
        self.rt_db = RealtimeDB(self.rt_path)
        self.project_svc = ProjectService(self.meta_db, self.rt_db)
        
        self.mock_auth = MagicMock()
        self.setup_svc = SetupService(self.mock_auth, self.project_svc)

        self.project_id = self.meta_db.post_project(ProjectCreate(
            name="BMS Scan Project", elec_meter_no="METER_BMS_SCAN", server_account_id=1
        ))

    def tearDown(self):
        try: os.close(self.db_fd)
        except Exception: pass
        try: os.close(self.rt_fd)
        except Exception: pass
        try:
            if os.path.exists(self.db_path): os.remove(self.db_path)
        except Exception: pass
        try:
            if os.path.exists(self.rt_path): os.remove(self.rt_path)
        except Exception: pass

    def test_pylontech_bms_driver_methods(self):
        mock_transport = MagicMock()
        # Mock registers for read_info: Serial Number ASCII "PYLON_SN_TEST01"
        sn_text = "PYLON_SN_TEST01"
        regs = []
        for i in range(0, len(sn_text), 2):
            b1 = ord(sn_text[i])
            b2 = ord(sn_text[i+1]) if i+1 < len(sn_text) else 0
            regs.append((b1 << 8) | b2)
        
        mock_transport.read_holding_registers.return_value = regs
        mock_transport.read_input_registers.return_value = [512, 100, 0, 0, 95, 99, 65]

        driver = PylontechBMSDriver(mock_transport, slave_id=1)
        info = driver.read_info()
        self.assertIsNotNone(info)
        self.assertIn("PYLON_SN_TEST01", info["serial_number"])
        self.assertEqual(info["brand"], "Pylontech")
        self.assertEqual(info["capacity_kwh"], 4.8)

        telemetry = driver.read_telemetry()
        self.assertIsNotNone(telemetry)
        self.assertEqual(telemetry["bms_batt_soc"], 95)
        self.assertEqual(telemetry["bms_batt_soh"], 99)

    def test_scan_batteries_flow(self):
        mock_transport = MagicMock()
        # Responsive at slave 2 only
        def mock_read_holding(address, count, slave=1):
            if slave == 2:
                return [0x5059, 0x4C4F, 0x4E5F, 0x3030, 0x3200] # ASCII "PYLON_002"
            return None

        mock_transport.read_holding_registers.side_effect = mock_read_holding

        found_ids = self.setup_svc.scan_batteries(
            transport=mock_transport,
            project_id=self.project_id,
            driver_class=PylontechBMSDriver,
            slave_start=1,
            slave_end=3
        )
        self.assertEqual(len(found_ids), 1)
        
        saved_batt = self.project_svc.get_battery_by_id(found_ids[0])
        self.assertIsNotNone(saved_batt)
        self.assertEqual(saved_batt.brand, "Pylontech")

if __name__ == "__main__":
    unittest.main()
