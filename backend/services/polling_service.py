import time
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import importlib
from backend.db_manager import CacheDB
from backend.services.project_service import ProjectService
from backend.communication.modbus_tcp import ModbusTCP
from backend.communication.modbus_rtu import ModbusRTU
from backend.services.normalization_service import NormalizationService
from backend.services.fault_service import FaultService
from backend.services.string_monitoring_service import StringMonitoringService
from backend.models.polling import ProjectPollBatch
from backend.db_manager import CacheDB, RealtimeDB
from backend.core import settings

logger = logging.getLogger(__name__)

class PollingService:
    def __init__(self, project_svc: ProjectService, cache_db: CacheDB, realtime_db: RealtimeDB = None):
        self.project_svc = project_svc
        self.cache_db = cache_db
        self.realtime_db = realtime_db
        self.normalization = NormalizationService()
        self.fault_service = FaultService()
        self.string_monitor = StringMonitoringService(cache_db)
        self.transports = {}
        self._transport_lock = threading.Lock()
        
        # Bộ đếm lỗi kết nối cho từng Inverter (6 lần mới báo lỗi truyền thông)
        self._inv_fail_counts: Dict[int, int] = {}
        
        # Caching logic
        self._config_cache = []
        self._last_refresh = 0

    def _get_transport(self, comm_id: Optional[int]):
        if not comm_id:
            comm_id = 1
            
        with self._transport_lock:
            if comm_id in self.transports:
                return self.transports[comm_id]

            # Truy vấn cấu hình truyền thông từ DB
            config = self.project_svc.metadata_db.get_comm_id(comm_id)
            if not config:
                logger.error(f"[PollingService] Communication config ID {comm_id} not found in database. Fallback to ID 1.")
                config = self.project_svc.metadata_db.get_comm_id(1)
                if not config:
                    # Nếu DB hoàn toàn rỗng hoặc lỗi, fallback về cấu hình mặc định trong code
                    logger.critical("[PollingService] Database comm_config table is completely empty!")
                    t = ModbusRTU(
                        port=settings.MODBUS_PORT,
                        baudrate=settings.MODBUS_BAUDRATE,
                        retries=settings.RETRIES,
                        multi_master=settings.MODBUS_MULTI_MASTER
                    )
                    t.connect()
                    self.transports[comm_id] = t
                    return t

            # Tạo kết nối dựa vào config
            if config.comm_type == "TCP":
                host = config.host or "127.0.0.1"
                port = config.port or 502
                timeout = config.timeout or 1.0
                t = ModbusTCP(host=host, port=port, timeout=timeout)
                t.connect()
                self.transports[comm_id] = t
                logger.info(f"[PollingService] Connected ModbusTCP for comm_id={comm_id} ({host}:{port})")
                return t
            else:
                com_port = config.com_port or "/dev/ttyUSB0"
                baudrate = config.baudrate or 9600
                databits = config.databits or 8
                parity = config.parity or "N"
                stopbits = config.stopbits or 1
                timeout = config.timeout or 1.0
                t = ModbusRTU(
                    port=com_port.strip(),
                    baudrate=baudrate,
                    bytesize=databits,
                    parity=parity,
                    stopbits=stopbits,
                    timeout=timeout,
                    retries=settings.RETRIES,
                    multi_master=bool(getattr(config, 'multi_master', settings.MODBUS_MULTI_MASTER))
                )
                t.connect()
                self.transports[comm_id] = t
                logger.info(f"[PollingService] Connected ModbusRTU for comm_id={comm_id} ({com_port} @ {baudrate})")
                return t

    def get_polling_config(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Lấy cấu hình polling (Projects & Inverters) từ RAM Cache hoặc Database"""
        now = time.time()
        config_changed = False
        try:
            if self.project_svc and self.project_svc.metadata_db:
                if self.project_svc.metadata_db.get_setting("polling_config_changed", "false") == "true":
                    config_changed = True
                    self.project_svc.metadata_db.set_setting("polling_config_changed", "false")
        except Exception:
            pass

        if force_refresh or config_changed or not self._config_cache or (now - self._last_refresh > 5):
            if config_changed or force_refresh or not self._config_cache:
                logger.info("[PollingService] Refreshing Polling Configuration Cache from DB (config updated)...")
            else:
                logger.debug("[PollingService] Refreshing Polling Configuration Cache from DB (timer)...")
            projects = self.project_svc.get_projects()
            new_cache = []
            
            for project in projects:
                inverters = self.project_svc.get_inverters_by_project(project.id)
                active_inverters = [inv for inv in inverters if getattr(inv, "is_active", True)]
                
                # EVN: Lấy danh sách meters của project
                meters = self.project_svc.get_meters_by_project(project.id)
                active_meters = [m for m in meters if getattr(m, "is_active", True)]

                new_cache.append({
                    "project": project,
                    "inverters": active_inverters,
                    "meters": active_meters
                })
            
            self._config_cache = new_cache
            self._last_refresh = now
        
        return self._config_cache

    def _get_driver(self, brand: str, transport, slave_id: int, model: str = None):
        if not brand or not model:
            return None
        
        b_low = brand.lower()
        m_low = model.lower()
        
        # Explicit mapping cho các model Solis phổ biến
        if b_low == "solis":
            if "s6" in m_low or "eh3p99" in m_low:
                from backend.drivers.inverters.solis_S6_EH3P99_9K10_NV_YD_H import SolisS6HybridDriver
                return SolisS6HybridDriver(transport, slave_id=slave_id)
            elif "110k" in m_low:
                from backend.drivers.inverters.solis_110k import Solis110k
                return Solis110k(transport, slave_id=slave_id)
            elif "100k" in m_low:
                from backend.drivers.inverters.solis_100k import Solis100k
                return Solis100k(transport, slave_id=slave_id)

        # Try loading from backend.drivers.inverters subfolder first
        clean_brand = b_low.replace(" ", "_").replace("-", "_").replace(".", "_")
        clean_model = m_low.replace(" ", "_").replace("-", "_").replace(".", "_")
        
        # Sanitize for classname: Brandmodel (Sungrow_SG110CX -> Sungrowsg110cx)
        clean_model_class = m_low.replace(" ", "").replace("-", "").replace("_", "").replace(".", "")
        class_name = f"{brand.capitalize()}{clean_model_class}"
        
        module_names = [
            f"backend.drivers.inverters.{clean_brand}_{clean_model}",
            f"backend.drivers.{clean_brand}_{clean_model}"
        ]
        
        for mod_name in module_names:
            try:
                module = importlib.import_module(mod_name)
                driver_class = getattr(module, class_name)
                return driver_class(transport, slave_id=slave_id)
            except (ImportError, AttributeError):
                continue
                
        logger.error(f"Failed to load driver {class_name} for brand {brand} model {model}")
        return None

    def poll_project_batch(self, project_id: int, inverters: List[Any] = None) -> ProjectPollBatch:
        """Đọc dữ liệu từ tất cả Inverter của Project, gom vào một Batch object."""
        if inverters is None:
            all_invs = self.project_svc.get_inverters_by_project(project_id)
            active_inverters = [inv for inv in all_invs if getattr(inv, "is_active", True)]
        else:
            active_inverters = [inv for inv in inverters if getattr(inv, "is_active", True)]
        
        batch = ProjectPollBatch(project_id=project_id, timestamp=datetime.now().astimezone().isoformat())
        
        if not active_inverters:
            logger.info(f"[PollingService] Project ID {project_id} has 0 active inverters configured.")
            return batch

        for inv in active_inverters:
            if not getattr(inv, "is_active", True):
                continue
            # Kiểm tra xem cổng truyền thông của inverter có đang bị quét tự động không
            is_scanning = self.project_svc.metadata_db.get_setting(f"scanning_comm_{inv.comm_id}", "false") == "true"
            if is_scanning:
                logger.info(f"[PollingService] Inverter {inv.id} (comm_id={inv.comm_id}) is busy due to scanning. Closing active transport & skipping polling.")
                with self._transport_lock:
                    if inv.comm_id in self.transports:
                        try:
                            self.transports[inv.comm_id].close()
                        except Exception:
                            pass
                        del self.transports[inv.comm_id]
                continue

            # Kiểm tra xem cổng truyền thông có được cấu hình là Master hay không
            comm_config = self.project_svc.metadata_db.get_comm_id(inv.comm_id)
            if comm_config and not getattr(comm_config, 'is_master', True):
                logger.info(f"[PollingService] Inverter {inv.id} is on a Slave comm port (comm_id={inv.comm_id}). Skipping polling.")
                continue

            try:
                transport = self._get_transport(inv.comm_id)
                driver = self._get_driver(inv.brand, transport, inv.slave_id, inv.model)
                
                raw_data = None
                if driver:
                    try:
                        with transport.arbiter.operation("polling"):
                            raw_data = driver.read_all()
                    except Exception as e:
                        logger.warning(f"Driver read error for Inverter {inv.id}: {e}")

                if not raw_data:
                    # --- LOGIC XỬ LÝ MẤT KẾT NỐI (TIMEOUT/DISCONNECT) ---
                    logger.warning(f"Inverter {inv.id} (Slave {inv.slave_id}) failed to respond. Generating zero-payload.")
                    
                    # 1. Lấy dữ liệu cũ từ Cache hoặc RealtimeDB để bảo toàn sản lượng E
                    last_ac = self.cache_db.get_ac_cache(inv.id)
                    e_daily, e_total, e_monthly, delta_e = 0.0, 0.0, 0.0, 0.0
                    last_ts_str = None
                    
                    if last_ac:
                        e_daily = last_ac.get("E_daily", 0.0)
                        e_total = last_ac.get("E_total", 0.0)
                        e_monthly = last_ac.get("E_monthly", 0.0)
                        delta_e = last_ac.get("delta_E_monthly", 0.0)
                        last_ts_str = last_ac.get("updated_at")
                    else:
                        # Fallback to RealtimeDB if Cache is empty
                        last_real = self.realtime_db.get_latest_inverter_ac_realtime(inv.id)
                        if last_real:
                            e_daily = last_real.E_daily
                            e_total = last_real.E_total
                            e_monthly = last_real.E_monthly
                            delta_e = last_real.delta_E_monthly
                            last_ts_str = last_real.created_at

                    # --- KIỂM TRA RESET E THEO NGÀY/THÁNG ---
                    now = datetime.now()
                    if last_ts_str:
                        try:
                            # Xử lý format timestamp (có thể có hoặc không có T)
                            if "T" not in last_ts_str:
                                last_ts = datetime.fromisoformat(last_ts_str.replace(" ", "T"))
                            else:
                                last_ts = datetime.fromisoformat(last_ts_str)
                            
                            # Nếu qua ngày mới -> Reset E_daily
                            if last_ts.date() < now.date():
                                logger.info(f"New day detected for disconnected Inverter {inv.id}. Resetting E_daily.")
                                e_daily = 0.0
                            
                            # Nếu qua tháng mới -> Reset E_monthly
                            if last_ts.year < now.year or last_ts.month < now.month:
                                logger.info(f"New month detected for disconnected Inverter {inv.id}. Resetting E_monthly.")
                                e_monthly = 0.0
                                delta_e = 0.0
                        except Exception as e:
                            logger.warning(f"Failed to parse timestamp {last_ts_str} for Inverter {inv.id}: {e}")

                    # 2. Tạo bản tin AC "Zero" (P, U, I = 0) - Sử dụng các key mà CacheDB.upsert_inverter_ac mong đợi
                    clean = {
                        "p_inv_w": 0.0, "q_inv_var": 0.0, "pf": 0.0, "grid_hz": 0.0,
                        "v_a": 0.0, "v_b": 0.0, "v_c": 0.0,
                        "i_a": 0.0, "i_b": 0.0, "i_c": 0.0,
                        "e_daily": e_daily, "e_total": e_total,
                        "e_monthly": e_monthly, "delta_E_monthly": delta_e,
                        "ir": 0.0, "temp_c": 0.0
                    }
                    batch.ac_data.append({"inverter_id": inv.id, "data": clean})

                    # 3. Tạo bản tin MPPT & String "Zero"
                    for i in range(1, inv.mppt_count + 1):
                        batch.mppt_data.append({"inverter_id": inv.id, "mppt_index": i, "data": {"v_mppt": 0.0, "i_mppt": 0.0, "p_mppt": 0.0}})
                        for s_idx in [2*i-1, 2*i]:
                            batch.string_data.append({"inverter_id": inv.id, "string_id": s_idx, "mppt_id": i, "i_string": 0.0})

                    # 4. Gán lỗi mất kết nối (Chỉ báo lỗi sau 6 lần thất bại liên tiếp)
                    self._inv_fail_counts[inv.id] = self._inv_fail_counts.get(inv.id, 0) + 1
                    
                    if self._inv_fail_counts[inv.id] >= 15:
                        logger.error(f"Inverter {inv.id} failed 15 times. Reporting COMMUNICATION_FAULT.")
                        status_code = 9 
                        fault_code = 1501
                        # Reset biến đếm sau khi báo lỗi theo yêu cầu
                        self._inv_fail_counts[inv.id] = 0
                        
                        errors_payload = [{
                            "fault_code": 1501,
                            "fault_description": "LỖI TRUYỀN THÔNG",
                            "repair_instruction": "Kiểm tra cáp RS485/Ethernet và địa chỉ Slave ID",
                            "severity": "DISCONNECT",
                            "created_at": batch.timestamp
                        }]
                        batch.error_data.append({
                            "inverter_id": inv.id, "status_code": status_code, "fault_code": fault_code,
                            "status_text": "LỖI TRUYỀN THÔNG", "fault_json": json.dumps(errors_payload, ensure_ascii=False)
                        })
                    else:
                        # Nếu chưa đủ 6 lần, lấy trạng thái cũ từ cache để tránh báo lỗi ảo
                        status_code = 0
                        fault_code = 0
                        status_text = "UNKNOWN"
                        fault_json = "[]"
                        
                        if last_ac:
                            # Thử lấy trạng thái lỗi cuối cùng từ cache
                            last_err = self.cache_db.get_error_cache(inv.id)
                            if last_err:
                                status_code = last_err.get("status_code", 0)
                                fault_code = last_err.get("fault_code", 0)
                                status_text = last_err.get("status_text", "UNKNOWN")
                                fault_json = last_err.get("fault_json", "[]")
                        
                        batch.error_data.append({
                            "inverter_id": inv.id, "status_code": status_code, "fault_code": fault_code,
                            "status_text": status_text, "fault_json": fault_json
                        })
                    continue

                # --- LOGIC XỬ LÝ KHI CÓ DỮ LIỆU THÀNH CÔNG ---
                # Reset bộ đếm lỗi khi có dữ liệu thành công
                self._inv_fail_counts[inv.id] = 0
                
                last_ac = self.cache_db.get_ac_cache(inv.id)
                
                # Kiểm tra lệch múi giờ (Time Drift)
                if last_ac and last_ac.get("updated_at"):
                    try:
                        last_ts = datetime.fromisoformat(last_ac["updated_at"].replace(" ", "T"))
                        new_ts = datetime.fromisoformat(batch.timestamp.replace(" ", "T"))
                        if last_ts.tzinfo is not None:
                            last_ts = last_ts.astimezone().replace(tzinfo=None)
                        if new_ts.tzinfo is not None:
                            new_ts = new_ts.astimezone().replace(tzinfo=None)
                        if new_ts <= last_ts:
                            logger.warning(f"[PollingService] Time drift detected for inverter {inv.id}: new timestamp {batch.timestamp} <= last timestamp {last_ac['updated_at']}. Skipping this sample.")
                            continue
                    except Exception as e:
                        logger.warning(f"[PollingService] Error checking time drift for inverter {inv.id}: {e}")

                clean = self.normalization.normalize(raw_data, last_data=last_ac, device_id=inv.id)
                batch.ac_data.append({"inverter_id": inv.id, "data": clean})
                
                # Lưu vào CacheDB (RAM)
                self.cache_db.upsert_inverter_ac(inv.id, project_id, clean)
                
                # Log rõ ràng kết quả đọc thành công để theo dõi trên console/docker
                p_ac_val = clean.get("p_inv_w", 0.0)
                v_a_val = clean.get("v_a", 0.0)
                e_daily_val = clean.get("e_daily", 0.0)
                soc_val = clean.get("bms_batt_soc", 0)
                logger.info(f"[PollingService] Inverter ID {inv.id} (SN: {inv.serial_number}, Slave {inv.slave_id}, {inv.brand} {inv.model}) READ SUCCESS -> P_ac={p_ac_val}W, V_a={v_a_val}V, E_daily={e_daily_val}kWh, BMS SOC={soc_val}%")

                # MPPT & String
                for i in range(1, inv.mppt_count + 1):
                    v_mppt = clean.get(f"mppt_{i}_voltage", 0.0)
                    i_mppt = clean.get(f"mppt_{i}_current", 0.0)
                    batch.mppt_data.append({
                        "inverter_id": inv.id, "mppt_index": i, 
                        "data": {"v_mppt": v_mppt, "i_mppt": i_mppt, "p_mppt": round(v_mppt * i_mppt, 2)}
                    })
                    for s_idx in [2*i-1, 2*i]:
                        i_str = clean.get(f"string_{s_idx}_current", 0.0)
                        batch.string_data.append({"inverter_id": inv.id, "string_id": s_idx, "mppt_id": i, "i_string": i_str})

                # Lưu Battery Cache vào CacheDB nếu có số liệu Pin
                battery_data = raw_data.get("battery")
                if isinstance(battery_data, list) and len(battery_data) > 0:
                    self.cache_db.upsert_battery_cache(project_id, battery_data)
                elif clean.get("bms_batt_soc") is not None or clean.get("inv_batt_u") is not None or clean.get("bms_batt_u") is not None:
                    batt_obj = {
                        "serial_number": f"BATT_{inv.serial_number}_{inv.slave_id}",
                        "project_id": project_id,
                        "inv_batt_u": clean.get("inv_batt_u", 0.0),
                        "inv_batt_i": clean.get("inv_batt_i", 0.0),
                        "inv_batt_p": clean.get("inv_batt_p", 0.0),
                        "bms_batt_u": clean.get("bms_batt_u", 0.0),
                        "bms_batt_i": clean.get("bms_batt_i", 0.0),
                        "bms_batt_p": clean.get("bms_batt_p", 0.0),
                        "bms_batt_soc": clean.get("bms_batt_soc", 0.0),
                        "bms_batt_soh": clean.get("bms_batt_soh", 0.0),
                        "batt_direction": clean.get("batt_direction", -1),
                        "e_charge_daily": clean.get("e_charge_daily", 0.0),
                        "e_discharge_daily": clean.get("e_discharge_daily", 0.0),
                        "e_charge_total": clean.get("e_charge_total", 0.0),
                        "e_discharge_total": clean.get("e_discharge_total", 0.0),
                        "bms_min_cell_temp": clean.get("bms_min_cell_temp", 0.0),
                        "bms_max_cell_temp": clean.get("bms_max_cell_temp", 0.0),
                        "bms_min_cell_volt": clean.get("bms_min_cell_volt", 0.0),
                        "bms_max_cell_volt": clean.get("bms_max_cell_volt", 0.0),
                    }
                    self.cache_db.upsert_battery_cache(project_id, [batt_obj])

                # Lưu Load Cache vào CacheDB nếu có số liệu Phụ tải
                load_data = raw_data.get("load")
                if load_data and isinstance(load_data, dict):
                    self.cache_db.upsert_load_cache(project_id, load_data)
                elif clean.get("p_load_w") is not None or clean.get("s_backup_load") is not None:
                    self.cache_db.upsert_load_cache(project_id, clean)

                # Lưu Meter Cache vào CacheDB nếu có số liệu Công tơ / Grid
                grid_data = raw_data.get("grid")
                if grid_data and isinstance(grid_data, dict):
                    meter_cache_data = {
                        "V_a": grid_data.get("u_a", clean.get("v_a")),
                        "V_b": grid_data.get("u_b", clean.get("v_b")),
                        "V_c": grid_data.get("u_c", clean.get("v_c")),
                        "I_a": grid_data.get("i_a", clean.get("i_a")),
                        "I_b": grid_data.get("i_b", clean.get("i_b")),
                        "I_c": grid_data.get("i_c", clean.get("i_c")),
                        "P_total": grid_data.get("p_grid_total", clean.get("p_grid_w", 0.0)),
                        "Q_total": grid_data.get("q_grid_total", clean.get("q_grid_w", 0.0)),
                        "S_total": grid_data.get("s_grid_total", 0.0),
                        "PF": grid_data.get("pf", clean.get("pf")),
                        "F": grid_data.get("f", clean.get("grid_hz")),
                        "imp_pt_today": grid_data.get("e_import_today", grid_data.get("e_import_total", 0.0)),
                        "exp_pt_today": grid_data.get("e_export_today", grid_data.get("e_export_total", 0.0)),
                        "e_pt_import": grid_data.get("e_import_total", 0.0),
                        "e_pt_export": grid_data.get("e_export_total", 0.0),
                    }
                    self.cache_db.upsert_meter_cache(meter_id=inv.id, project_id=project_id, data=meter_cache_data)
                elif clean.get("p_grid_w") is not None:
                    meter_cache_data = {
                        "V_a": clean.get("v_a"), "V_b": clean.get("v_b"), "V_c": clean.get("v_c"),
                        "I_a": clean.get("i_a"), "I_b": clean.get("i_b"), "I_c": clean.get("i_c"),
                        "P_total": clean.get("p_grid_w", 0.0),
                        "Q_total": clean.get("q_grid_w", 0.0),
                        "PF": clean.get("pf"),
                        "F": clean.get("grid_hz"),
                        "imp_pt_today": clean.get("e_grid_import_daily", 0.0),
                        "exp_pt_today": clean.get("e_grid_export_daily", 0.0),
                    }
                    self.cache_db.upsert_meter_cache(meter_id=inv.id, project_id=project_id, data=meter_cache_data)

                # Error Logic
                status_code = raw_data.get("state_id", 0)
                fault_code = raw_data.get("fault_code", 0)
                
                if inv.brand.upper() == "SOLIS":
                    errors_payload = []
                    state_snapshot = self.fault_service.get_state_snapshot(inv.brand, status_code)
                    errors_payload.append({
                        "fault_code": state_snapshot["code"],
                        "fault_description": state_snapshot["name"],
                        "repair_instruction": state_snapshot["description"],
                        "severity": state_snapshot["severity"],
                        "created_at": batch.timestamp
                    })
                    
                    from backend.services.fault_mappings import FAULT_MAPS, UNIFIED_FAULTS
                    fault_regs = ["fault_code_1", "fault_code_2", "fault_code_3", "fault_code_4", "fault_code_5"]
                    solis_map = FAULT_MAPS.get("SOLIS", {})
                    
                    for idx, reg_key in enumerate(fault_regs):
                        reg_val = raw_data.get(reg_key, 0)
                        if reg_val > 0:
                            for bit in range(16):
                                if (reg_val & (1 << bit)) > 0:
                                    fault_id = (3067 + idx) * 100 + bit
                                    fault_info = solis_map.get(fault_id)
                                    if fault_info:
                                        unified_code = fault_info["id_unified"]
                                        raw_inst = fault_info.get("repair_instruction", "")
                                        errors_payload.append({
                                            "fault_code": unified_code,
                                            "fault_description": UNIFIED_FAULTS.get(unified_code, fault_info["name"]),
                                            "repair_instruction": self.fault_service.format_repair_instruction(inv.brand, fault_id, raw_inst),
                                            "severity": fault_info["severity"],
                                            "created_at": batch.timestamp
                                        })
                elif inv.brand.upper() == "GOODWE":
                    errors_payload = []
                    state_snapshot = self.fault_service.get_state_snapshot(inv.brand, status_code)
                    errors_payload.append({
                        "fault_code": state_snapshot["code"],
                        "fault_description": state_snapshot["name"],
                        "repair_instruction": state_snapshot["description"],
                        "severity": state_snapshot["severity"],
                        "created_at": batch.timestamp
                    })
                    
                    from backend.services.fault_mappings import FAULT_MAPS, UNIFIED_FAULTS
                    goodwe_map = FAULT_MAPS.get("GOODWE", {})
                    if fault_code > 0:
                        for bit in range(32):
                            if (fault_code & (1 << bit)) > 0:
                                fault_id = 1 << bit
                                fault_info = goodwe_map.get(fault_id)
                                if fault_info:
                                    unified_code = fault_info["id_unified"]
                                    raw_inst = fault_info.get("repair_instruction", "")
                                    errors_payload.append({
                                        "fault_code": unified_code,
                                        "fault_description": UNIFIED_FAULTS.get(unified_code, fault_info["name"]),
                                        "repair_instruction": self.fault_service.format_repair_instruction(inv.brand, fault_id, raw_inst),
                                        "severity": fault_info["severity"],
                                        "created_at": batch.timestamp
                                    })
                elif inv.brand.upper() == "HUAWEI":
                    errors_payload = []
                    state_snapshot = self.fault_service.get_state_snapshot(inv.brand, status_code)
                    errors_payload.append({
                        "fault_code": state_snapshot["code"],
                        "fault_description": state_snapshot["name"],
                        "repair_instruction": state_snapshot["description"],
                        "severity": state_snapshot["severity"],
                        "created_at": batch.timestamp
                    })
                    
                    from backend.services.fault_mappings import FAULT_MAPS, UNIFIED_FAULTS
                    huawei_map = FAULT_MAPS.get("HUAWEI", {})
                    active_faults = raw_data.get("active_faults", [])
                    
                    for raw_fault in active_faults:
                        fault_info = huawei_map.get(raw_fault)
                        if fault_info:
                            unified_code = fault_info["id_unified"]
                            raw_inst = fault_info.get("repair_instruction", "")
                            errors_payload.append({
                                "fault_code": unified_code,
                                "fault_description": UNIFIED_FAULTS.get(unified_code, fault_info["name"]),
                                "repair_instruction": self.fault_service.format_repair_instruction(inv.brand, raw_fault, raw_inst),
                                "severity": fault_info["severity"],
                                "created_at": batch.timestamp
                            })
                else:
                    errors_payload = self.fault_service.get_inverter_status_payload(inv.brand, status_code, fault_code, batch.timestamp)
                # Check String Open Circuit
                current_strings_data = [{"string_index": s["string_id"], "I_string": s["i_string"]} for s in batch.string_data if s["inverter_id"] == inv.id]
                string_faults = self.string_monitor.process_strings(inv.id, current_strings_data, batch.timestamp)
                if string_faults:
                    errors_payload.extend(string_faults)

                # Lọc lỗi theo yêu cầu:
                # 1. Nếu có lỗi 23 (String mất dòng đột ngột), loại bỏ mã lỗi 1 ("ĐANG VẬN HÀNH") ra khỏi payload
                has_fault_23 = any(item.get("fault_code") == 23 for item in errors_payload)
                if has_fault_23:
                    errors_payload = [item for item in errors_payload if item.get("fault_code") != 1]
                else:
                    # 2. Nếu không có lỗi 23 nhưng có lỗi thực sự khác, lọc bỏ trạng thái STABLE (ví dụ: ĐANG VẬN HÀNH)
                    has_real_fault = any(item.get("severity") in ("WARNING", "ERROR", "DISCONNECT") for item in errors_payload)
                    if has_real_fault:
                        errors_payload = [item for item in errors_payload if item.get("severity") != "STABLE"]

                state_snapshot = self.fault_service.get_state_snapshot(inv.brand, status_code)
                batch.error_data.append({
                    "inverter_id": inv.id, "status_code": status_code, "fault_code": fault_code,
                    "status_text": state_snapshot["name"], "fault_json": json.dumps(errors_payload, ensure_ascii=False)
                })
                
            except Exception as e:
                logger.error(f"Critical error polling inverter {inv.id}: {e}", exc_info=True)
        
        # Giải phóng socket TCP sau mỗi chu kỳ đọc để tránh chiếm giữ port 502 dài hạn
        with self._transport_lock:
            for comm_id, transport in list(self.transports.items()):
                if hasattr(transport, "close"):
                    try:
                        transport.close()
                    except Exception:
                        pass
            self.transports.clear()
        
        logger.debug(f"Project {project_id}: Polled {len(batch.ac_data)} inverters in this batch.")
        return batch

    def poll_meters(self, project_id: int, meters: List[Any]):
        """Đọc dữ liệu từ Meter (điểm đấu nối lưới) và lưu vào CacheDB."""
        for m in meters:
            # Kiểm tra xem cổng truyền thông của meter có đang bị quét tự động không
            is_scanning = self.project_svc.metadata_db.get_setting(f"scanning_comm_{m.comm_id}", "false") == "true"
            if is_scanning:
                logger.info(f"[PollingService] Meter {m.id} (comm_id={m.comm_id}) is busy due to scanning. Skipping polling for this device.")
                continue

            # Kiểm tra xem cổng truyền thông có được cấu hình là Master hay không
            comm_config = self.project_svc.metadata_db.get_comm_id(m.comm_id)
            if comm_config and not getattr(comm_config, 'is_master', True):
                logger.info(f"[PollingService] Meter {m.id} is on a Slave comm port (comm_id={m.comm_id}). Skipping polling.")
                continue

            try:
                # Meter thường dùng RTU
                transport = self._get_transport(m.comm_id)
                driver = self._get_meter_driver(m.brand, transport, m.slave_id, m.model)
                if not driver:
                    continue

                with transport.arbiter.operation("polling_meter"):
                    raw_data = driver.read_all()
                
                if not raw_data:
                    logger.warning(f"Meter {m.id} (Slave {m.slave_id}) failed to respond.")
                    continue

                # Lưu vào CacheDB
                self.cache_db.upsert_meter_cache(m.id, project_id, raw_data)
                logger.debug(f"Poll & Cache Success - Meter {m.id}")

            except Exception as e:
                logger.error(f"Error polling meter {m.id}: {e}")

    def scan_meters(
        self, 
        brand: str, 
        model: str, 
        comm_type: str, 
        host: Optional[str] = None, 
        port: Optional[int] = None,
        com_port: Optional[str] = None,
        baudrate: int = 9600,
        slave_start: int = 1,
        slave_end: int = 247
    ) -> List[Dict]:
        """
        Quét các thiết bị Meter trong một dải Slave ID.
        Trả về danh sách các meter tìm thấy.
        """
        from backend.communication.modbus_tcp import ModbusTCP
        from backend.communication.modbus_rtu import ModbusRTU
        
        transport = None
        if comm_type.upper() == "TCP":
            transport = ModbusTCP(host, port)
        else:
            transport = ModbusRTU(com_port, baudrate)
            
        if not transport.connect():
            logger.error("[Polling] Scan meters: Failed to connect to %s:%s", host or com_port, port or baudrate)
            return []
            
        found_meters = []
        try:
            for sid in range(slave_start, slave_end + 1):
                logger.info("[Polling] Scanning meter brand=%s model=%s sid=%s", brand, model, sid)
                driver = self._get_meter_driver(brand, transport, sid, model)
                if not driver:
                    continue
                    
                # Thử đọc một tập dữ liệu cơ bản
                data = driver.read_all()
                if data:
                    # Đọc Serial Number (nếu driver hỗ trợ)
                    sn = driver.read_serial_number()
                    found_meters.append({
                        "brand": brand,
                        "model": model,
                        "slave_id": sid,
                        "serial_number": sn, # Có thể là None
                        "data_preview": {
                            "V_a": data.get("v_a"),
                            "P_total": data.get("p_total")
                        }
                    })
        finally:
            transport.close()
            
        return found_meters

    def _get_meter_driver(self, brand: str, transport, slave_id: int, model: str):
        """Tải driver cho Meter."""
        if not brand or not model:
            return None
        
        clean_brand = brand.lower().replace(" ", "_").replace("-", "_").replace(".", "_")
        clean_model = model.lower().replace(" ", "_").replace("-", "_").replace(".", "_")
        
        clean_model_class = model.lower().replace(" ", "").replace("-", "").replace("_", "").replace(".", "")
        class_name = f"Meter{brand.capitalize()}{clean_model_class}"
        
        module_names = [
            f"backend.drivers.meters.{clean_brand}_{clean_model}",
            f"backend.drivers.{clean_brand}_{clean_model}"
        ]
        
        for mod_name in module_names:
            try:
                module = importlib.import_module(mod_name)
                driver_class = getattr(module, class_name)
                return driver_class(transport, slave_id=slave_id)
            except (ImportError, AttributeError):
                continue

        # Fallback về Base class nếu chưa có driver cụ thể
        logger.warning(f"Meter driver {class_name} not found, using MeterDriverBase")
        from backend.drivers.meters.meter_base import MeterDriverBase
        return MeterDriverBase(transport, slave_id=slave_id)
