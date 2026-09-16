import unittest
import tempfile
import os

from backend.db_manager import MetadataDB, RealtimeDB
from backend.services.project_service import ProjectService
from backend.models.project import ProjectCreate
from backend.models.battery import BatteryCreate
from backend.api.battery_api import (
    _normalize_battery_body,
    update_battery,
    get_battery_id,
    list_batteries,
    create_battery,
    delete_battery
)

class TestBatteryAPI(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.rt_fd, self.rt_path = tempfile.mkstemp()
        self.meta_db = MetadataDB(self.db_path)
        self.rt_db = RealtimeDB(self.rt_path)
        self.svc = ProjectService(self.meta_db, self.rt_db)

        p_id = self.meta_db.post_project(ProjectCreate(
            name="API Test Project", elec_meter_no="METER_API"
        ))
        self.project_id = p_id

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

    def test_normalize_battery_body(self):
        norm1 = _normalize_battery_body({"status": "Ngưng hoạt động"})
        self.assertFalse(norm1.get("is_active"))

        norm2 = _normalize_battery_body({"is_active": "true"})
        self.assertTrue(norm2.get("is_active"))

        norm3 = _normalize_battery_body({"usage_start_at": ""})
        self.assertIsNone(norm3.get("usage_start_at"))

    def test_api_endpoints_flow(self):
        # 1. Create via API helper
        create_res = create_battery(svc=self.svc, body={
            "project_id": self.project_id,
            "brand": "Pylontech",
            "model": "US3000C",
            "serial_number": "PYLON_001",
            "capacity_kwh": 3.5,
            "capacity_ah": 74.0,
            "is_active": True
        })
        self.assertEqual(create_res["serial_number"], "PYLON_001")
        self.assertEqual(create_res["status"], "Hoạt động")
        batt_id = create_res["id"]

        # 2. List all
        all_res = list_batteries(svc=self.svc)
        self.assertEqual(len(all_res), 1)

        # 3. Get single
        get_res = get_battery_id(battery_id=batt_id, svc=self.svc)
        self.assertEqual(get_res["brand"], "Pylontech")

        # 4. Patch
        patch_res = update_battery(battery_id=batt_id, svc=self.svc, body={"status": "Ngưng hoạt động", "capacity_kwh": 4.0})
        self.assertFalse(patch_res["is_active"])
        self.assertEqual(patch_res["status"], "Ngưng hoạt động")
        self.assertEqual(patch_res["capacity_kwh"], 4.0)

if __name__ == "__main__":
    unittest.main()
