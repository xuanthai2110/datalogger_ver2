import time
from datetime import datetime
import json
import logging
import threading
import queue
from backend.db_manager import CacheDB, RealtimeDB
from backend.services.project_service import ProjectService
from backend.services.energy_service import EnergyService
from backend.services.max_tracking_service import MaxTrackingService
from backend.services.fault_service import FaultService
from backend.services.telemetry_service import TelemetryService
from backend.services.uploader_service import UploaderService
from backend.models.realtime import (
    InverterErrorCreate
)
from backend.core import settings

logger = logging.getLogger(__name__)

class LogicWorker(threading.Thread):
    def __init__(self, cache_db, project_svc: ProjectService, realtime_db, fault_service, build_tele_worker=None):
        super().__init__()
        self.cache_db = cache_db
        self.project_svc = project_svc
        self.realtime_db = realtime_db
        self.fault_logic = fault_service
        self.energy_service = EnergyService(realtime_db)
        self.max_service = MaxTrackingService(realtime_db)
        self.telemetry = TelemetryService(realtime_db)
        self.build_tele_worker = build_tele_worker
        self.daemon = True
        self._stop_event = threading.Event()
        self._trigger_queue = queue.Queue()

    def trigger_project(self, project_id: int):
        """Kích hoạt xử lý logic cho 1 project (gọi bởi PollingWorker sau khi commit batch)."""
        self._trigger_queue.put(project_id)

    def run(self):
        logger.info("Logic worker started.")
        while not self._stop_event.is_set():
            try:
                # Chờ sự kiện kích hoạt theo project_id (chặn tối đa 1s để kiểm tra stop_event)
                try:
                    project_id = self._trigger_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                self._process(project_id)
                self._trigger_queue.task_done()
                
            except Exception as e:
                logger.error(f"Logic worker error: {e}", exc_info=True)

    def _process(self, project_id: int):
        """Xử lý logic (Energy, Max Tracking, Faults) cho toàn bộ Inverter trong 1 Project vừa quét xong."""
        ac_rows = self.cache_db.get_ac_cache_by_project(project_id)
        # Xác định khung giờ ban đêm (16:00 - 07:00) theo yêu cầu
        current_time_dt = datetime.now()
        current_hour = current_time_dt.hour
        is_night_period = (current_hour >= 16 or current_hour < 7)

        inverter_ids = [ac["inverter_id"] for ac in ac_rows]
        is_sleep = self.telemetry.is_all_inverters_sleep(inverter_ids, self.cache_db)

        any_inv_changed = False
        for ac in ac_rows:
            inv_id = ac["inverter_id"]
            polling_time = ac["updated_at"]
            
            # 1. Tính toán sản lượng năng lượng (Energy Calculation)
            e_state = self.energy_service.calculate(inv_id, ac["E_total"])
            
            # 2. Cập nhật Max Tracking (Vmax, Pmax, Imax)
            mppts = self.cache_db.get_mppt_cache_by_inverter(inv_id)
            strings = self.cache_db.get_string_cache_by_inverter(inv_id)
            
            inv_p_dc = sum(m.get("p_mppt", m.get("P_mppt", 0)) for m in mppts) if mppts else 0
            
            hold_zero_max = self.max_service.prepare_for_poll(inv_id, polling_time)
            if hold_zero_max:
                self.cache_db.reset_mppt_max(inv_id)
                self.cache_db.reset_string_max(inv_id)
            else:
                maxes = self.max_service.update(inv_id, mppts, strings, polling_time=polling_time)
                for mppt_idx, m_max in maxes.get("mppt", {}).items():
                    self.cache_db.update_mppt_max(inv_id, mppt_idx, m_max["Max_V"], m_max["Max_I"], m_max["Max_P"])
                for str_id, s_max_i in maxes.get("string", {}).items():
                    self.cache_db.update_string_max(inv_id, str_id, s_max_i)
            
            # 3. Xử lý Lỗi và Trạng thái (Faults & States)
            err_cache = self.cache_db.get_error_cache(inv_id)
            s_code = err_cache["status_code"] if err_cache else 0
            f_code = err_cache["fault_code"] if err_cache else 0
            f_json = err_cache["fault_json"] if err_cache else None
            
            payload, changed, last_severity = self.fault_logic.process(inv_id, project_id, s_code, f_code, polling_time, f_json)
            
            # Lấy mã trạng thái hợp nhất và severity hiện tại
            unified_code = payload[0]["fault_code"] if payload else 0
            current_severity = payload[0]["severity"] if payload else "STABLE"
            
            # --- ĐIỀU CHỈNH LOGIC BAN ĐÊM (16:00 - 07:00) ---
            # Chỉ trong khoảng 16:00 đến 07:00, severity của các mã trạng thái này mới là STABLE
            stable_night_codes = [1, 2, 3, 4, 9, 12, 14, 15, 19, 22]
            if is_night_period and unified_code in stable_night_codes:
                current_severity = "STABLE"

            # Quyết định có trigger build telemetry tức thời hay không
            should_trigger = changed
            
            # Nếu ban đêm thì không trigger bất kỳ trạng thái hoặc lỗi nào ngay lập tức
            if is_night_period:
                should_trigger = False
            else:
                # Điều kiện 1: Bỏ qua trigger nếu là các trạng thái dừng/ngủ/chờ/hở mạch và công suất thấp (< 2kW)
                if unified_code in [2, 4, 22, 23] and inv_p_dc < 2000:
                    should_trigger = False
                
                # Điều kiện 2: Bỏ qua trigger khi phục hồi từ lỗi về Stable
                if last_severity in ["ERROR", "WARNING", "DISCONNECT"] and current_severity == "STABLE":
                    should_trigger = False
                
            if should_trigger:
                any_inv_changed = True
            
            # Chỉ ghi log lỗi vào database nếu KHÔNG phải ban đêm
            if changed and not is_sleep and not is_night_period:
                for err_dict in payload:
                    err_rec = InverterErrorCreate(
                        project_id=project_id,
                        inverter_id=inv_id,
                        fault_code=err_dict["fault_code"],
                        fault_description=err_dict["fault_description"],
                        repair_instruction=err_dict["repair_instruction"],
                        severity=err_dict["severity"],
                        created_at=err_dict["created_at"]
                    )
                    self.realtime_db.post_inverter_error(err_rec)

            # 4. Cập nhật Cache với các giá trị vừa tính toán (Monthly/Delta Energy)
            self.cache_db.update_ac_processed(inv_id, e_state["E_monthly"], e_state["current_delta"])
                
        # 5. Kích hoạt Build Telemetry ngay lập tức CHỈ KHI có thay đổi trạng thái/lỗi
        if any_inv_changed:
            logger.info(f"LogicWorker: Status/Fault changed for project {project_id}. Triggering immediate build.")
            self._trigger_immediate(project_id)

        # 6. Publish telemetry realtime lên MQTT (chu kỳ 10s/lần)
        self._publish_realtime_mqtt(project_id)

    def _trigger_immediate(self, project_id: int):
        if self.build_tele_worker:
            logger.info(f"LogicWorker: Triggering immediate telemetry build for project {project_id}")
            self.build_tele_worker.trigger_now(project_id)

    def _publish_realtime_mqtt(self, project_id: int):
        try:
            logger.debug(f"[RealtimeMQTT] Starting check for project {project_id}")
            if not self.build_tele_worker:
                logger.warning("[RealtimeMQTT] Skip: build_tele_worker is None")
                return
            if not hasattr(self.build_tele_worker, "mqtt_sub"):
                logger.warning("[RealtimeMQTT] Skip: build_tele_worker has no 'mqtt_sub' attribute")
                return
            if not self.build_tele_worker.mqtt_sub:
                logger.warning("[RealtimeMQTT] Skip: build_tele_worker.mqtt_sub is None")
                return
            
            proj_meta = self.project_svc.get_project(project_id)
            if not proj_meta:
                logger.warning(f"[RealtimeMQTT] Skip: project metadata for ID {project_id} not found")
                return
                
            mqtt_sub = self.build_tele_worker.mqtt_sub
            server_id = proj_meta.server_id
            logger.debug(f"[RealtimeMQTT] Project {project_id} -> Server ID: {server_id}")
            
            # Lấy client_ids đang active từ mqtt_sub (chuẩn hóa so sánh để tránh lệch kiểu dữ liệu int vs str)
            client_ids = []
            if hasattr(mqtt_sub, "realtime_clients"):
                logger.debug(f"[RealtimeMQTT] mqtt_sub.realtime_clients keys: {list(mqtt_sub.realtime_clients.keys())}")
                matched_key = None
                for k in mqtt_sub.realtime_clients.keys():
                    if str(k) == str(server_id):
                        matched_key = k
                        break
                if matched_key is not None:
                    client_ids = list(mqtt_sub.realtime_clients[matched_key])
            else:
                logger.warning("[RealtimeMQTT] mqtt_sub has no 'realtime_clients' attribute")
                
            db_mode = getattr(proj_meta, "telemetry_mode", "Realtime")
            logger.debug(f"[RealtimeMQTT] Active clients: {client_ids}, mode: {db_mode}")
            
            # Bỏ qua nếu Web Local không chạy Realtime và cũng không có client nào đang xem
            if db_mode in ("Periodic", "Offline") and not client_ids:
                logger.debug(f"[RealtimeMQTT] Skip: db_mode is {db_mode} and no active clients")
                return
                
            invs = self.project_svc.get_inverters_by_project(project_id)
            active_invs = [inv for inv in invs if getattr(inv, "is_active", True)]
            logger.debug(f"[RealtimeMQTT] Active inverters: {[inv.id for inv in active_invs]}")
            
            payload_list = self.telemetry.build_payload_from_cache(
                project_id, server_id, active_invs, self.cache_db
            )
            
            if not payload_list:
                logger.warning("[RealtimeMQTT] Skip: build_payload_from_cache returned empty payload")
                return
                
            payload = payload_list[0]
            logger.debug("[RealtimeMQTT] Payload generated successfully")
            
            # 1. Gửi Broadcast lên topic mặc định chỉ khi Web Local bật chế độ Realtime (DB là Realtime)
            if db_mode == "Realtime":
                broadcast_topic = f"telemetry/realtime/{server_id}"
                logger.debug(f"[RealtimeMQTT] Publishing broadcast to {broadcast_topic}")
                mqtt_sub.publish(broadcast_topic, payload)
            
            # 2. Gửi đích danh tới từng client_id đang hoạt động (nếu có)
            for cid in client_ids:
                topic = f"telemetry/realtime/{server_id}/{cid}"
                logger.debug(f"[RealtimeMQTT] Publishing targeted telemetry to {topic}")
                mqtt_sub.publish(topic, payload)
        except Exception as e:
            logger.error(f"LogicWorker: Failed to publish realtime MQTT for project {project_id}: {e}", exc_info=True)

