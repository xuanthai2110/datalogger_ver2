"""
backend/services/zero_export_service.py

Zero Export Service — Điều khiển công suất Inverter để ngăn xuất ngược lưới điện.

Thuật toán:
    Mỗi chu kỳ (10s):
    1. Kiểm tra ZE enabled, EVN lock, Server schedule → nếu có → dừng chu kỳ này
    2. Đọc P_meter từ CacheDB
    3. Nếu Meter stale/mất (tăng fail_count):
       - fail_count < threshold: giữ nguyên setpoint
       - fail_count >= threshold: set 0 kW + báo METER_FAULT
    4. Tính P_grid thực tế theo hướng CT
    5. So sánh với deadband → quyết định INCREASE/DECREASE/HOLD
    6. Phân bổ setpoint cho từng Inverter và ghi Modbus
"""
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any

from backend.core import settings as app_settings
from backend.db_manager.cache import CacheDB
from backend.models.zero_export import ZeroExportConfig, ZeroExportStatus

logger = logging.getLogger(__name__)

# Fault code riêng cho METER_FAULT trong ZeroExport
METER_FAULT_CODE = 9001
METER_FAULT_DESCRIPTION = "LỖI ĐO LƯỜNG METER (ZERO EXPORT)"
METER_FAULT_INSTRUCTION = "Kiểm tra kết nối Meter (RS485/Ethernet), nguồn điện Meter, và địa chỉ Slave ID"


class ZeroExportService:
    """Service điều khiển Zero Export — ngăn xuất ngược lưới điện."""

    def __init__(
        self,
        cache_db: CacheDB,
        metadata_db,
        control_service,
        polling_service,
        schedule_service=None,
    ):
        self.cache_db = cache_db
        self.metadata_db = metadata_db
        self.control_service = control_service
        self.polling_service = polling_service
        self.schedule_service = schedule_service

        # Runtime state — lưu trong RAM (reset khi restart service)
        self._status_lock = threading.RLock()
        self._statuses: Dict[int, ZeroExportStatus] = {}
        # {project_id: ZeroExportStatus}
        self._last_enabled: Dict[int, bool] = {}

    # =========================================================
    # CONFIG — Đọc / Ghi
    # =========================================================
    def get_config(self, project_id: int) -> ZeroExportConfig:
        """Đọc cấu hình Zero Export từ MetadataDB."""
        raw = self.metadata_db.get_zero_export_config(project_id)
        return ZeroExportConfig(**raw)

    def save_config(self, project_id: int, config_dict: dict):
        """Lưu cấu hình Zero Export vào MetadataDB (partial update)."""
        self.metadata_db.set_zero_export_config(project_id, config_dict)

    # =========================================================
    # STATUS — Đọc runtime status
    # =========================================================
    def get_status(self, project_id: int) -> ZeroExportStatus:
        """Trả về trạng thái runtime hiện tại của Zero Export."""
        with self._status_lock:
            # 1. Thử đọc từ CacheDB trước để đồng bộ liên process (web và polling)
            try:
                cached = self.cache_db.get_zero_export_status_cache(project_id)
                if cached:
                    self._statuses[project_id] = ZeroExportStatus(
                        project_id=project_id,
                        enabled=cached.get("enabled", False),
                        suspended_by=cached.get("suspended_by"),
                        p_grid_w=cached.get("p_grid_w"),
                        p_inv_total_w=cached.get("p_inv_total_w"),
                        p_inv_setpoint_w=cached.get("p_inv_setpoint_w"),
                        last_action=cached.get("last_action"),
                        meter_fail_count=cached.get("meter_fail_count", 0),
                        last_updated=cached.get("last_updated"),
                    )
            except Exception as e:
                logger.error("[ZeroExportService] Failed to read status from CacheDB: %s", e)

            if project_id not in self._statuses:
                cfg = self.get_config(project_id)
                self._statuses[project_id] = ZeroExportStatus(
                    project_id=project_id,
                    enabled=cfg.enabled,
                )
            return self._statuses[project_id]

    def _update_status(self, project_id: int, **kwargs):
        """Cập nhật trạng thái runtime (thread-safe + ghi xuống CacheDB)."""
        from dataclasses import asdict
        with self._status_lock:
            if project_id not in self._statuses:
                # Cố gắng load từ CacheDB hoặc khởi tạo
                self.get_status(project_id)

            status = self._statuses[project_id]
            for k, v in kwargs.items():
                if hasattr(status, k):
                    setattr(status, k, v)
            status.last_updated = datetime.now().isoformat()
            
            # 2. Đồng bộ xuống CacheDB để container web có thể đọc được
            try:
                self.cache_db.upsert_zero_export_status_cache(project_id, asdict(status))
            except Exception as e:
                logger.error("[ZeroExportService] Failed to sync status to CacheDB: %s", e)

    # =========================================================
    # HELPER — Tính P_grid theo hướng CT
    # =========================================================
    @staticmethod
    def calc_p_grid(p_meter_w: float, meter_direction: str, p_inv_total_w: float) -> float:
        """Tính công suất lưới thực tế (W) từ số đo Meter theo hướng lắp CT.

        Quy ước kết quả:
            P_grid > 0  → Đang import từ lưới (tải > solar) — OK
            P_grid < 0  → Đang export ra lưới (solar > tải) — CẦN GIẢM

        Args:
            p_meter_w:        Giá trị P_total đọc từ Meter (W)
            meter_direction:  Hướng lắp CT
            p_inv_total_w:    Tổng công suất AC đang phát của các Inverter (W)
        """
        d = (meter_direction or "GRID_SIDE").upper()

        if d == "GRID_SIDE":
            # CT xuôi phía lưới: P_meter > 0 = import
            return p_meter_w

        elif d == "GRID_SIDE_REVERSED":
            # CT ngược phía lưới: P_meter > 0 = export → đảo dấu
            return -p_meter_w

        elif d == "LOAD_SIDE":
            # CT đo phía tải: P_meter = P_load, P_grid = P_load - P_inv
            return p_meter_w - p_inv_total_w

        elif d == "LOAD_SIDE_REVERSED":
            # CT ngược phía tải: P_meter < 0 = P_load thực
            return (-p_meter_w) - p_inv_total_w

        else:
            logger.warning("[ZeroExport] Unknown meter_direction '%s', treating as GRID_SIDE", meter_direction)
            return p_meter_w

    # =========================================================
    # HELPER — Kiểm tra Meter còn fresh không
    # =========================================================
    @staticmethod
    def _is_meter_data_fresh(meter_data: Optional[dict]) -> bool:
        """Trả về True nếu dữ liệu Meter còn hợp lệ (có updated_at và không quá 30s)."""
        if not meter_data:
            return False
        updated_at = meter_data.get("updated_at")
        if not updated_at:
            return False
        try:
            ts = datetime.fromisoformat(updated_at)
            age_sec = (datetime.now() - ts).total_seconds()
            # Nếu timestamp có tzinfo thì strip ra để so sánh
            if ts.tzinfo is not None:
                from datetime import timezone
                ts = ts.astimezone().replace(tzinfo=None)
                age_sec = (datetime.now() - ts).total_seconds()
            return age_sec <= 30.0
        except Exception:
            return False

    # =========================================================
    # HELPER — Lấy tổng công suất inverter hiện tại
    # =========================================================
    def _get_inv_total_power_w(self, project_id: int) -> float:
        """Tổng P_ac của tất cả inverter active trong project (từ CacheDB)."""
        ac_rows = self.cache_db.get_ac_cache_by_project(project_id)
        return sum(row.get("P_ac", 0.0) or 0.0 for row in ac_rows)

    # =========================================================
    # HELPER — Lấy rated power tối đa của project
    # =========================================================
    def _get_inv_rated_power_w(self, project_id: int) -> float:
        """Tổng công suất định mức AC của các inverter active (W)."""
        project_item = self.control_service._find_project_item(project_id)
        if not project_item:
            return 0.0
        inverters = self.control_service._active_inverters(project_item)
        total = sum(self.control_service._inverter_rated_kw(inv) for inv in inverters)
        return total * 1000.0  # kW → W

    # =========================================================
    # HELPER — Reset tất cả Inverter về 100%
    # =========================================================
    def _reset_inverters_to_100(self, project_id: int):
        """Gỡ giới hạn công suất — cho Inverter chạy tối đa."""
        project_item = self.control_service._find_project_item(project_id)
        if not project_item:
            return
        inverters = self.control_service._active_inverters(project_item)
        if inverters:
            self.control_service._reset_inverters(inverters, control_source="ZERO_EXPORT")

    # =========================================================
    # HELPER — Set Inverter về 0 kW (chế độ an toàn)
    # =========================================================
    def _set_inverters_to_zero(self, project_id: int):
        """Set công suất Inverter về 0 W — chế độ an toàn khi mất meter."""
        project_item = self.control_service._find_project_item(project_id)
        if not project_item:
            return
        inverters = self.control_service._active_inverters(project_item)
        if not inverters:
            return

        # Tạo setpoints dict với mọi inverter = 0 kW
        setpoints = {inv.id: 0.0 for inv in inverters}
        self.control_service._write_maxp_setpoints_kw(inverters, setpoints, schedule_id=-9001)
        logger.warning(
            "[ZeroExport] project=%s SET ALL INVERTERS TO 0 kW — METER_FAULT safe mode",
            project_id,
        )

    # =========================================================
    # HELPER — Ghi setpoint phân bổ
    # =========================================================
    def _apply_setpoint_w(self, project_id: int, p_inv_target_w: float):
        """Phân bổ P_target cho từng Inverter theo tỉ lệ công suất và ghi Modbus."""
        project_item = self.control_service._find_project_item(project_id)
        if not project_item:
            return
        inverters = self.control_service._active_inverters(project_item)
        if not inverters:
            return

        # Đọc công suất hiện tại để phân bổ tỉ lệ
        power_map = self.control_service._collect_read_power_w_map(inverters)
        setpoints_kw = self.control_service._build_maxp_setpoints_kw(
            inverters,
            limit_watts=p_inv_target_w,
            power_w_by_id=power_map,
        )
        self.control_service._write_maxp_setpoints_kw(inverters, setpoints_kw, schedule_id=-9000)

        logger.info(
            "[ZeroExport] project=%s applied setpoints_kw=%s",
            project_id,
            {iid: round(kw, 2) for iid, kw in setpoints_kw.items()},
        )

    # =========================================================
    # CORE — Vòng lặp điều khiển chính
    # =========================================================
    def run_cycle(self, project_id: int):
        """Chạy một chu kỳ Zero Export cho project.

        Gọi từ ZeroExportWorker mỗi 10s.
        """
        try:
            cfg = self.get_config(project_id)

            # ----- Edge Detection: Theo dõi thay đổi trạng thái bật/tắt để ghi Audit Log -----
            last_enabled = self._last_enabled.get(project_id)
            if last_enabled is None:
                # Lần chạy đầu tiên: Khởi tạo RAM mà không sinh log
                self._last_enabled[project_id] = cfg.enabled
            elif last_enabled != cfg.enabled:
                if cfg.enabled:
                    # OFF -> ON: Bật Zero Export
                    logger.info(f"[ZeroExport] project={project_id} turned ON. Writing ZERO_EXPORT_START to audit log.")
                    self.metadata_db.write_control_audit_log(
                        project_id=project_id,
                        inverter_id=None,
                        command_type="ZERO_EXPORT_START",
                        control_source="ZERO_EXPORT",
                        requested_value=1.0,
                        actual_value=None,
                        status="SUCCESS"
                    )
                else:
                    # ON -> OFF: Tắt Zero Export -> Tự động trả inverter về 100%
                    logger.info(f"[ZeroExport] project={project_id} turned OFF. Resetting inverters to 100% and writing ZERO_EXPORT_STOP to audit log.")
                    self._reset_inverters_to_100(project_id)
                    self.metadata_db.write_control_audit_log(
                        project_id=project_id,
                        inverter_id=None,
                        command_type="ZERO_EXPORT_STOP",
                        control_source="ZERO_EXPORT",
                        requested_value=0.0,
                        actual_value=None,
                        status="SUCCESS"
                    )
                self._last_enabled[project_id] = cfg.enabled

            # ----- Guard 1: ZE bị tắt vĩnh viễn bởi user -----
            if not cfg.enabled:
                self._update_status(project_id, enabled=False, suspended_by=None, last_action="DISABLED")
                return

            self._update_status(project_id, enabled=True)

            # ----- Guard 2: EVN đang giữ quyền điều khiển P -----
            if self.control_service.is_evn_locked_p(project_id):
                logger.debug("[ZeroExport] project=%s suspended: EVN lock active", project_id)
                self._update_status(project_id, suspended_by="EVN", last_action="HOLD")
                return

            # ----- Guard 3: Server/MQTT Schedule đang active -----
            if self.schedule_service and self.schedule_service.has_active_p_schedule(project_id):
                logger.debug("[ZeroExport] project=%s suspended: Server schedule active", project_id)
                self._update_status(project_id, suspended_by="SCHEDULE", last_action="HOLD")
                return

            # Đã qua hết guards → ZE được phép chạy
            self._update_status(project_id, suspended_by=None)

            # ----- Bước 1: Kiểm tra Meter -----
            if not cfg.meter_id:
                logger.warning("[ZeroExport] project=%s: No meter_id configured. Skip.", project_id)
                self._update_status(project_id, last_action="NO_METER")
                return

            meter_data = self.cache_db.get_meter_cache(cfg.meter_id)
            meter_fresh = self._is_meter_data_fresh(meter_data)

            # Lấy current fail count từ status
            current_status = self.get_status(project_id)
            fail_count = current_status.meter_fail_count

            if not meter_fresh:
                fail_count += 1
                logger.warning(
                    "[ZeroExport] project=%s Meter %s not fresh (fail %d/%d)",
                    project_id, cfg.meter_id, fail_count, cfg.meter_fail_threshold,
                )
                self._update_status(project_id, meter_fail_count=fail_count)

                if fail_count >= cfg.meter_fail_threshold:
                    # ----- METER_FAULT: Set Inverter về 0 kW -----
                    logger.error(
                        "[ZeroExport] project=%s METER_FAULT! Meter offline %d times → set inverters to 0 kW",
                        project_id, fail_count,
                    )
                    self._set_inverters_to_zero(project_id)
                    self._update_status(
                        project_id,
                        last_action="METER_FAULT",
                        p_grid_w=None,
                        p_inv_setpoint_w=0.0,
                    )
                else:
                    # Chưa đủ ngưỡng → giữ nguyên setpoint hiện tại
                    self._update_status(project_id, last_action="HOLD")
                return

            # Meter OK — reset fail counter
            if fail_count > 0:
                logger.info("[ZeroExport] project=%s Meter recovered after %d failures.", project_id, fail_count)
            self._update_status(project_id, meter_fail_count=0)

            # ----- Bước 2: Tính P_grid -----
            p_meter_w = float(meter_data.get("P_total") or 0.0)
            p_inv_total_w = self._get_inv_total_power_w(project_id)
            p_grid_w = self.calc_p_grid(p_meter_w, cfg.meter_direction, p_inv_total_w)

            self._update_status(project_id, p_grid_w=p_grid_w, p_inv_total_w=p_inv_total_w)

            # ----- Bước 3: Tính error và deadband -----
            error_w = p_grid_w - cfg.export_limit_w

            if abs(error_w) < cfg.deadband_w:
                # Trong vùng bất nhạy — không điều chỉnh
                logger.debug(
                    "[ZeroExport] project=%s P_grid=%.1fW error=%.1fW < deadband=%.1fW → HOLD",
                    project_id, p_grid_w, error_w, cfg.deadband_w,
                )
                self._update_status(project_id, last_action="HOLD")
                return

            # ----- Bước 4: Tính setpoint mới -----
            p_inv_rated_w = self._get_inv_rated_power_w(project_id)
            ramp_w = cfg.ramp_kw_per_step * 1000.0
            delta_w = min(abs(error_w) * cfg.gain, ramp_w)

            if error_w > 0:
                # P_grid > export_limit → Tải lớn hơn Solar → Tăng về tối đa
                p_inv_target_w = min(p_inv_total_w + delta_w, p_inv_rated_w)
                action = "INCREASE"
            else:
                # P_grid < export_limit → Solar lớn hơn Tải → Giảm công suất
                p_inv_target_w = max(p_inv_total_w - delta_w, 0.0)
                action = "DECREASE"

            logger.info(
                "[ZeroExport] project=%s P_grid=%.1fW error=%.1fW action=%s "
                "p_inv_now=%.1fW delta=%.1fW p_inv_target=%.1fW",
                project_id, p_grid_w, error_w, action,
                p_inv_total_w, delta_w, p_inv_target_w,
            )

            # ----- Bước 5: Ghi setpoint xuống Inverter -----
            self._apply_setpoint_w(project_id, p_inv_target_w)
            self._update_status(
                project_id,
                last_action=action,
                p_inv_setpoint_w=p_inv_target_w,
            )

        except Exception as e:
            logger.error("[ZeroExport] run_cycle error for project %s: %s", project_id, e, exc_info=True)
