import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.services.zero_export_service import ZeroExportService, METER_FAULT_CODE
from backend.models.zero_export import ZeroExportConfig, ZeroExportStatus


class TestZeroExportService(unittest.TestCase):
    def setUp(self):
        self.cache_db = MagicMock()
        self.metadata_db = MagicMock()
        self.control_service = MagicMock()
        self.polling_service = MagicMock()
        self.schedule_service = MagicMock()

        self.service = ZeroExportService(
            cache_db=self.cache_db,
            metadata_db=self.metadata_db,
            control_service=self.control_service,
            polling_service=self.polling_service,
            schedule_service=self.schedule_service,
        )

        # Cấu hình Mock cache_db mặc định
        self.cache_db.get_zero_export_status_cache.return_value = None

        # Mock mặc định config
        self.default_config_dict = {
            "project_id": 1,
            "enabled": True,
            "meter_id": 2,
            "meter_direction": "GRID_SIDE",
            "export_limit_w": 0.0,
            "deadband_w": 200.0,
            "gain": 1.0,
            "ramp_kw_per_step": 50.0,
            "meter_fail_threshold": 10,
        }
        self.metadata_db.get_zero_export_config.return_value = self.default_config_dict

    def test_calc_p_grid_grid_side(self):
        # GRID_SIDE: P_meter > 0 = import
        p_grid = self.service.calc_p_grid(1500.0, "GRID_SIDE", 5000.0)
        self.assertEqual(p_grid, 1500.0)

    def test_calc_p_grid_grid_side_reversed(self):
        # GRID_SIDE_REVERSED: P_meter > 0 = export → đảo dấu
        p_grid = self.service.calc_p_grid(1500.0, "GRID_SIDE_REVERSED", 5000.0)
        self.assertEqual(p_grid, -1500.0)

    def test_calc_p_grid_load_side(self):
        # LOAD_SIDE: P_grid = P_meter - P_inv
        p_grid = self.service.calc_p_grid(6500.0, "LOAD_SIDE", 5000.0)
        self.assertEqual(p_grid, 1500.0)

    def test_calc_p_grid_load_side_reversed(self):
        # LOAD_SIDE_REVERSED: P_grid = -P_meter - P_inv
        p_grid = self.service.calc_p_grid(-6500.0, "LOAD_SIDE_REVERSED", 5000.0)
        self.assertEqual(p_grid, 1500.0)

    def test_is_meter_data_fresh(self):
        now_str = datetime.now().isoformat()
        self.assertTrue(self.service._is_meter_data_fresh({"updated_at": now_str}))

        old_str = (datetime.now() - timedelta(seconds=35)).isoformat()
        self.assertFalse(self.service._is_meter_data_fresh({"updated_at": old_str}))

        self.assertFalse(self.service._is_meter_data_fresh(None))
        self.assertFalse(self.service._is_meter_data_fresh({}))

    def test_run_cycle_disabled(self):
        self.default_config_dict["enabled"] = False
        self.service.run_cycle(1)
        self.control_service.apply_zero_export_setpoint.assert_not_called()
        status = self.service.get_status(1)
        self.assertFalse(status.enabled)

    def test_run_cycle_evn_locked(self):
        self.control_service.is_evn_locked_p.return_value = True
        self.service.run_cycle(1)
        self.control_service.apply_zero_export_setpoint.assert_not_called()
        status = self.service.get_status(1)
        self.assertEqual(status.suspended_by, "EVN")

    def test_run_cycle_schedule_active(self):
        self.control_service.is_evn_locked_p.return_value = False
        self.schedule_service.has_active_p_schedule.return_value = True
        self.service.run_cycle(1)
        self.control_service.apply_zero_export_setpoint.assert_not_called()
        status = self.service.get_status(1)
        self.assertEqual(status.suspended_by, "SCHEDULE")

    def test_run_cycle_meter_stale_under_threshold(self):
        self.control_service.is_evn_locked_p.return_value = False
        self.schedule_service.has_active_p_schedule.return_value = False

        # Mock meter offline
        self.cache_db.get_meter_cache.return_value = None

        # Chạy cycle lần 1
        self.service.run_cycle(1)
        status = self.service.get_status(1)
        self.assertEqual(status.meter_fail_count, 1)
        self.assertEqual(status.last_action, "HOLD")
        self.control_service.apply_zero_export_setpoint.assert_not_called()

    def test_run_cycle_meter_stale_over_threshold(self):
        self.control_service.is_evn_locked_p.return_value = False
        self.schedule_service.has_active_p_schedule.return_value = False
        self.cache_db.get_meter_cache.return_value = None

        # Giả lập đã thất bại 9 lần trước
        status = self.service.get_status(1)
        status.meter_fail_count = 9

        # Inverter mock target
        inv1 = MagicMock(id=1, rate_ac_kw=50.0, capacity_kw=None, is_active=True)
        self.control_service._find_project_item.return_value = {
            "project": MagicMock(id=1),
            "inverters": [inv1],
        }
        self.control_service._active_inverters.return_value = [inv1]

        # Chạy cycle lần 10
        self.service.run_cycle(1)

        self.assertEqual(status.meter_fail_count, 10)
        self.assertEqual(status.last_action, "METER_FAULT")
        self.control_service._write_maxp_setpoints_kw.assert_called_once()
        # Đối số kw setpoint ghi xuống cho inv1 phải bằng 0.0
        setpoints_arg = self.control_service._write_maxp_setpoints_kw.call_args[0][1]
        self.assertEqual(setpoints_arg[1], 0.0)

    def test_run_cycle_decrease_power(self):
        self.control_service.is_evn_locked_p.return_value = False
        self.schedule_service.has_active_p_schedule.return_value = False

        # Mock meter online, trả về P_total = -1500W (đang export ngược 1500W)
        now_str = datetime.now().isoformat()
        self.cache_db.get_meter_cache.return_value = {
            "P_total": -1500.0,
            "updated_at": now_str,
        }

        # Mock inverters
        inv1 = MagicMock(id=1, rate_ac_kw=50.0, capacity_kw=None, is_active=True)
        self.control_service._find_project_item.return_value = {
            "project": MagicMock(id=1),
            "inverters": [inv1],
        }
        self.control_service._active_inverters.return_value = [inv1]
        self.control_service._inverter_rated_kw.return_value = 50.0

        # Mock current inverter power = 30000W (30kW)
        self.cache_db.get_ac_cache_by_project.return_value = [{"P_ac": 30000.0}]

        # Chạy cycle
        self.service.run_cycle(1)

        status = self.service.get_status(1)
        self.assertEqual(status.last_action, "DECREASE")
        # Target power = 30000W - 1500W * 1.0 (gain) = 28500W
        # Phải gọi phân bổ setpoint
        self.control_service._build_maxp_setpoints_kw.assert_called_once()
        limit_watts_arg = self.control_service._build_maxp_setpoints_kw.call_args[1]["limit_watts"]
        self.assertEqual(limit_watts_arg, 28500.0)

    def test_run_cycle_increase_power(self):
        self.control_service.is_evn_locked_p.return_value = False
        self.schedule_service.has_active_p_schedule.return_value = False

        # Mock meter online, trả về P_total = 1000W (đang import từ lưới 1000W)
        now_str = datetime.now().isoformat()
        self.cache_db.get_meter_cache.return_value = {
            "P_total": 1000.0,
            "updated_at": now_str,
        }

        # Mock inverters
        inv1 = MagicMock(id=1, rate_ac_kw=50.0, capacity_kw=None, is_active=True)
        self.control_service._find_project_item.return_value = {
            "project": MagicMock(id=1),
            "inverters": [inv1],
        }
        self.control_service._active_inverters.return_value = [inv1]
        self.control_service._inverter_rated_kw.return_value = 50.0

        # Mock current inverter power = 30000W (30kW)
        self.cache_db.get_ac_cache_by_project.return_value = [{"P_ac": 30000.0}]

        # Chạy cycle
        self.service.run_cycle(1)

        status = self.service.get_status(1)
        self.assertEqual(status.last_action, "INCREASE")
        # Target power = 30000W + 1000W * 1.0 (gain) = 31000W
        # Phải gọi phân bổ setpoint
        self.control_service._build_maxp_setpoints_kw.assert_called_once()
        limit_watts_arg = self.control_service._build_maxp_setpoints_kw.call_args[1]["limit_watts"]
        self.assertEqual(limit_watts_arg, 31000.0)


if __name__ == "__main__":
    unittest.main()
