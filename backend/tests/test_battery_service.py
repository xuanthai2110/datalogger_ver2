import unittest
import os
import tempfile
from unittest.mock import MagicMock, patch

from backend.db_manager import MetadataDB, RealtimeDB
from backend.services.project_service import ProjectService
from backend.services.setup_service import SetupService
from backend.models.battery import BatteryCreate, BatteryUpdate
from backend.models.project import ProjectCreate

class TestBatteryService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.rt_fd, self.rt_path = tempfile.mkstemp()
        self.metadata_db = MetadataDB(self.db_path)
        self.realtime_db = RealtimeDB(self.rt_path)
        self.project_svc = ProjectService(self.metadata_db, self.realtime_db)
        
        self.mock_auth = MagicMock()
        self.mock_auth.get_access_token.return_value = "mock_token_123"
        self.setup_svc = SetupService(self.mock_auth, self.project_svc)

        # Tạo 1 project giả lập có server_account_id = 1
        proj_id = self.metadata_db.post_project(ProjectCreate(
            elec_meter_no="METER_BATT_TEST",
            name="Test Battery Project",
            server_account_id=1
        ))
        self.metadata_db.update_project_sync(proj_id, server_id=99, status='approved')
        self.project_id = proj_id

    def tearDown(self):
        try:
            os.close(self.db_fd)
        except Exception:
            pass
        try:
            os.close(self.rt_fd)
        except Exception:
            pass
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass
        try:
            if os.path.exists(self.rt_path):
                os.remove(self.rt_path)
        except Exception:
            pass

    def test_battery_crud(self):
        # 1. Create battery
        batt_data = BatteryCreate(
            project_id=self.project_id,
            battery_index=1,
            serial_number="BATT_SN_001",
            brand="BYD",
            model="B-BOX HVS",
            capacity_kwh=10.2,
            capacity_ah=100.0,
            num_parallel_connections=1,
            cells_per_module=16,
            modules_in_series=4,
            is_active=True
        )
        res = self.project_svc.upsert_battery(batt_data)
        self.assertIsNotNone(res)
        self.assertEqual(res.serial_number, "BATT_SN_001")
        self.assertEqual(res.capacity_kwh, 10.2)

        # 2. Read battery
        batt_by_id = self.project_svc.get_battery_by_id(res.id)
        self.assertIsNotNone(batt_by_id)
        self.assertEqual(batt_by_id.brand, "BYD")

        batt_by_sn = self.project_svc.get_battery_by_serial("BATT_SN_001")
        self.assertIsNotNone(batt_by_sn)

        batteries = self.project_svc.get_batteries_by_project(self.project_id)
        self.assertEqual(len(batteries), 1)

        # 3. Patch battery
        self.project_svc.patch_battery(res.id, BatteryUpdate(capacity_kwh=12.5, is_active=False))
        updated_batt = self.project_svc.get_battery_by_id(res.id)
        self.assertEqual(updated_batt.capacity_kwh, 12.5)
        self.assertFalse(updated_batt.is_active)

        # 4. Delete battery
        self.project_svc.delete_battery(res.id)
        deleted_batt = self.project_svc.get_battery_by_id(res.id)
        self.assertIsNone(deleted_batt)

    @patch("requests.post")
    def test_initiate_battery_sync_create(self, mock_post):
        # Setup mock response for POST /api/batteries/requests/
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 888, "status": "pending"}
        mock_post.return_value = mock_resp

        # Create battery locally
        batt_data = BatteryCreate(
            project_id=self.project_id,
            battery_index=1,
            serial_number="BATT_SN_SYNC",
            brand="Solis Battery",
            model="5KWH"
        )
        res = self.project_svc.upsert_battery(batt_data)

        # Initiate sync
        req_id = self.setup_svc.initiate_battery_sync(res.id)
        self.assertEqual(req_id, 888)

        # Check local DB updated sync status
        updated = self.project_svc.get_battery_by_id(res.id)
        self.assertEqual(updated.server_request_id, 888)
        self.assertEqual(updated.sync_status, "pending")

    @patch("requests.post")
    def test_request_delete_battery_sync(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        batt_data = BatteryCreate(
            project_id=self.project_id,
            battery_index=1,
            serial_number="BATT_DEL_SYNC",
            brand="Tesla",
            model="Powerwall"
        )
        res = self.project_svc.upsert_battery(batt_data)
        self.project_svc.update_battery_sync(res.id, server_id=777, status="approved")

        success = self.setup_svc.request_delete_battery_sync(res.id)
        self.assertTrue(success)

if __name__ == "__main__":
    unittest.main()
