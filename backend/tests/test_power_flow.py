import unittest
import os
import tempfile
import shutil
from backend.db_manager.metadata import MetadataDB
from backend.db_manager.realtime import RealtimeDB
from backend.db_manager.cache import CacheDB
from backend.services.monitoring_service import MonitoringService

class TestPowerFlowService(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.meta_db_path = os.path.join(self.tmp_dir.name, "metadata.db")
        self.realtime_db_path = os.path.join(self.tmp_dir.name, "realtime.db")
        self.cache_db_path = os.path.join(self.tmp_dir.name, "cache.db")

        self.meta_db = MetadataDB(self.meta_db_path)
        self.realtime_db = RealtimeDB(self.realtime_db_path)
        self.cache_db = CacheDB(self.cache_db_path)

        self.svc = MonitoringService(self.meta_db, self.realtime_db, self.cache_db)

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_get_power_flow_empty(self):
        pf = self.svc.get_power_flow()
        self.assertIn("pv_kw", pf)
        self.assertIn("grid_kw", pf)
        self.assertIn("battery_kw", pf)
        self.assertIn("battery_soc", pf)
        self.assertEqual(pf["battery_soc"], 100)

    def test_get_power_flow_with_data(self):
        # Insert sample AC cache
        self.cache_db.upsert_inverter_ac(1, 1, {
            "p_inv_w": 497.0,
            "p_dc_w": 500.0,
        })
        with self.cache_db._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO battery_cache (serial_number, project_id, bms_batt_soc, inv_batt_p, bms_batt_p, updated_at)
                VALUES ('BATT_01', 1, 98, 1500.0, 1500.0, '2026-09-02T15:00:00')
            """)

        pf = self.svc.get_power_flow()
        self.assertEqual(pf["pv_kw"], 0.497)
        self.assertEqual(pf["pv_dc_kw"], 0.5)
        self.assertEqual(pf["inverter_kw"], 0.497)
        self.assertEqual(pf["battery_kw"], 1.5)
        self.assertEqual(pf["battery_soc"], 98)

if __name__ == "__main__":
    unittest.main()
