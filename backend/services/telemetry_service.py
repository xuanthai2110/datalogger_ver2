import logging
import json
from datetime import datetime
from typing import Any, List
from backend.db_manager import CacheDB

logger = logging.getLogger(__name__)

class TelemetryService:
    """Xây dựng telemetry payload từ CacheDB (RAM) để gửi lên server."""
    def __init__(self, realtime_db):
        self.realtime_db = realtime_db

    def build_payload_from_cache(self, project_id: int, server_id: int, inverters_meta: list, cache_db: CacheDB) -> list:
        now = datetime.now()
        payload_created_at = self._format_ts(now.isoformat())
        
        # Aggregate Project Data from Inverters in Cache
        total_p_ac = 0.0
        total_p_dc = 0.0
        total_e_daily = 0.0
        total_e_monthly = 0.0
        total_e_total = 0.0
        temp_list = []
        
        inverters_json = []
        # Priority mapping for project severity
        severity_priority = {"DISCONNECT": 3, "ERROR": 4, "WARNING": 2, "STABLE": 1}
        project_severity = "STABLE"

        active_inverters_meta = [inv for inv in inverters_meta if getattr(inv, "is_active", True)]
        for inv in active_inverters_meta:
            inv_id = inv.id
            
            # AC Data (from Cache)
            ac = cache_db.get_ac_cache(inv_id)
            if not ac: continue
            
            # Totals
            if ac.get("P_ac") is not None: total_p_ac += self._num(ac.get("P_ac"))
            if ac.get("E_daily") is not None: total_e_daily += self._num(ac.get("E_daily"))
            if ac.get("E_monthly") is not None: total_e_monthly += self._num(ac.get("E_monthly"))
            if ac.get("E_total") is not None: total_e_total += self._num(ac.get("E_total"))
            if ac.get("Temp_C") is not None:
                temp_list.append(self._num(ac.get("Temp_C")))
            
            # MPPT & Strings (from Cache)
            mppts_cache = cache_db.get_mppt_cache_by_inverter(inv_id)
            strings_cache = cache_db.get_string_cache_by_inverter(inv_id)
            
            inv_dc_sum = 0.0
            mppt_list = []
            for m in mppts_cache:
                m_idx = m["mppt_index"]
                if m.get("P_mppt") is not None:
                    inv_dc_sum += self._num(m.get("P_mppt"))
                
                m_strings = [
                    {
                        "string_index": s["string_id"],
                        "I_mppt": self._val(s.get("I_string")),
                        "Max_I": self._val(s.get("max_I")),
                        "created_at": payload_created_at
                    }
                    for s in strings_cache if s["mppt_id"] == m_idx
                ]
                
                mppt_list.append({
                    "mppt_index": m_idx,
                    "string_on_mppt": m.get("string_on_mppt", 2),
                    "V_mppt": self._val(m.get("V_mppt")),
                    "I_mppt": self._val(m.get("I_mppt")),
                    "P_mppt": self._val(m.get("P_mppt")),
                    "Max_I": self._val(m.get("Max_I")),
                    "Max_V": self._val(m.get("Max_V")),
                    "Max_P": self._val(m.get("Max_P")),
                    "created_at": payload_created_at,
                    "strings": m_strings
                })
            
            p_dc_val = ac.get("p_dc_w")
            if p_dc_val is not None:
                inverter_dc_power = self._num(p_dc_val)
            else:
                inverter_dc_power = inv_dc_sum

            total_p_dc += inverter_dc_power

            # Error Payload
            err_row = cache_db.get_error_cache(inv_id)
            errors = []
            if err_row:
                if err_row.get("fault_json"):
                    try:
                        errors = self._normalize_error_items(json.loads(err_row["fault_json"]), payload_created_at)
                    except Exception:
                        logger.warning(f"Invalid fault_json in cache for inverter {inv_id}. Using fallback error payload.")
                        errors = []
                else:
                    errors = self._normalize_error_items([{
                        "fault_code": err_row.get("fault_code", 0),
                        "fault_description": err_row.get("status_text") or err_row.get("fault_text") or "UNKNOWN",
                        "repair_instruction": "",
                        "severity": "STABLE",
                        "created_at": payload_created_at
                    }], payload_created_at)
            if not errors:
                errors = [self._default_error_item(err_row, ac, payload_created_at)]
            
            # Track Project Severity (highest among inverters)
            inv_severity = errors[0].get("severity", "STABLE") if errors else "STABLE"
            if severity_priority.get(inv_severity, 0) > severity_priority.get(project_severity, 0):
                project_severity = inv_severity

            inv_data = {
                "serial_number": inv.serial_number,
                "ac": {
                    "IR": self._val(ac.get("IR")),
                    "Temp_C": self._val(ac.get("Temp_C")),
                    "P_ac": self._val(ac.get("P_ac")),
                    "Q_ac": self._val(ac.get("Q_ac")),
                    "V_a": self._val(ac.get("V_a")),
                    "V_b": self._val(ac.get("V_b")),
                    "V_c": self._val(ac.get("V_c")),
                    "I_a": self._val(ac.get("I_a")),
                    "I_b": self._val(ac.get("I_b")),
                    "I_c": self._val(ac.get("I_c")),
                    "PF": self._val(ac.get("PF")),
                    "H": self._val(ac.get("H")),
                    "E_daily": self._val(ac.get("E_daily")),
                    "E_monthly": self._val(ac.get("E_monthly")),
                    "E_total": self._val(ac.get("E_total")),
                    "created_at": payload_created_at
                },
                "mppts": mppt_list,
                "errors": errors
            }
            inverters_json.append(inv_data)
        
        if not inverters_json: return []

        # Final Project Summary
        avg_temp = round(sum(temp_list) / len(temp_list), 1) if temp_list else None
        project_json = {
            "Temp_C": avg_temp,
            "P_ac": self._val(total_p_ac),
            "P_dc": self._val(total_p_dc),
            "E_daily": self._val(total_e_daily),
            "E_monthly": self._val(total_e_monthly),
            "E_total": self._val(total_e_total),
            "severity": project_severity,
            "created_at": payload_created_at
        }
            
        # Grid, Load, Batteries (Fetch from Cache or fallback to default null schema)
        grid_cache = None
        load_cache = None
        batteries_cache = []
        
        if hasattr(cache_db, "get_meter_cache_by_project"):
            meters = cache_db.get_meter_cache_by_project(project_id)
            if meters: grid_cache = meters[0]
            
        if hasattr(cache_db, "get_load_cache_by_project"):
            loads = cache_db.get_load_cache_by_project(project_id)
            if loads: load_cache = loads[0]

        if hasattr(cache_db, "get_battery_cache_by_project"):
            batteries_cache = cache_db.get_battery_cache_by_project(project_id)

        grid_json = self._default_grid_payload(payload_created_at, grid_cache)
        load_json = self._default_load_payload(payload_created_at, load_cache)
        batteries_json = [self._normalize_battery_item(b, payload_created_at) for b in batteries_cache] if batteries_cache else []

        payload = {
            "project": project_json,
            "inverters": inverters_json,
            "grid": grid_json,
            "load": load_json,
            "batteries": batteries_json
        }
        return [self._normalize_payload(payload)]

    def is_all_inverters_sleep(self, inverter_ids: list[int], cache_db: CacheDB) -> bool:
        if not inverter_ids:
            return False

        for inv_id in inverter_ids:
            ac_row = cache_db.get_ac_cache(inv_id)
            err_row = cache_db.get_error_cache(inv_id)
            if ac_row is None or err_row is None:
                return False

            status_text = (err_row.get("status_text") or "").strip().upper()
            if status_text != "SLEEP":
                return False

        return True

    def is_all_inverters_disconnect(self, inverter_ids: list[int], cache_db: CacheDB) -> bool:
        if not inverter_ids:
            return False

        for inv_id in inverter_ids:
            ac_row = cache_db.get_ac_cache(inv_id)
            err_row = cache_db.get_error_cache(inv_id)
            if ac_row is None or err_row is None:
                return False

            if self._get_error_severity(err_row) != "DISCONNECT":
                return False

        return True

    def _default_grid_payload(self, ts_now: str, raw_grid: dict | None = None) -> dict:
        g = raw_grid or {}
        return {
            "e_import_daily": self._val(g.get("e_import_daily")),
            "e_export_daily": self._val(g.get("e_export_daily")),
            "e_import_total": self._val(g.get("e_import_total")),
            "e_export_total": self._val(g.get("e_export_total")),
            "u_a": self._val(g.get("u_a")),
            "u_b": self._val(g.get("u_b")),
            "u_c": self._val(g.get("u_c")),
            "i_a": self._val(g.get("i_a")),
            "i_b": self._val(g.get("i_b")),
            "i_c": self._val(g.get("i_c")),
            "p_a": self._val(g.get("p_a")),
            "p_b": self._val(g.get("p_b")),
            "p_c": self._val(g.get("p_c")),
            "p_grid_total": self._val(g.get("p_grid_total")),
            "p_ac_grid_total": self._val(g.get("p_ac_grid_total")),
            "q_grid_total": self._val(g.get("q_grid_total")),
            "s_grid_total": self._val(g.get("s_grid_total")),
            "pf": self._val(g.get("pf")),
            "f": self._val(g.get("f")),
            "created_at": ts_now
        }

    def _default_load_payload(self, ts_now: str, raw_load: dict | None = None) -> dict:
        l = raw_load or {}
        return {
            "e_daily": self._val(l.get("e_daily")),
            "e_total": self._val(l.get("e_total")),
            "p_load": self._val(l.get("p_load")),
            "e_backup_daily": self._val(l.get("e_backup_daily")),
            "e_backup_total": self._val(l.get("e_backup_total")),
            "u_backup_a": self._val(l.get("u_backup_a")),
            "u_backup_b": self._val(l.get("u_backup_b")),
            "u_backup_c": self._val(l.get("u_backup_c")),
            "i_backup_a": self._val(l.get("i_backup_a")),
            "i_backup_b": self._val(l.get("i_backup_b")),
            "i_backup_c": self._val(l.get("i_backup_c")),
            "p_backup_a": self._val(l.get("p_backup_a")),
            "p_backup_b": self._val(l.get("p_backup_b")),
            "p_backup_c": self._val(l.get("p_backup_c")),
            "s_backup_load": self._val(l.get("s_backup_load")),
            "e_smart_daily": self._val(l.get("e_smart_daily")),
            "e_smart_total": self._val(l.get("e_smart_total")),
            "u_smart_a": self._val(l.get("u_smart_a")),
            "u_smart_b": self._val(l.get("u_smart_b")),
            "u_smart_c": self._val(l.get("u_smart_c")),
            "i_smart_a": self._val(l.get("i_smart_a")),
            "i_smart_b": self._val(l.get("i_smart_b")),
            "i_smart_c": self._val(l.get("i_smart_c")),
            "p_smart_a": self._val(l.get("p_smart_a")),
            "p_smart_b": self._val(l.get("p_smart_b")),
            "p_smart_c": self._val(l.get("p_smart_c")),
            "s_smart_load": self._val(l.get("s_smart_load")),
            "created_at": ts_now
        }

    def _normalize_battery_item(self, b: dict, ts_now: str) -> dict:
        return {
            "serial_number": b.get("serial_number"),
            "cycle_count": self._val(b.get("cycle_count")),
            "e_charge_daily": self._val(b.get("e_charge_daily")),
            "e_discharge_daily": self._val(b.get("e_discharge_daily")),
            "e_charge_total": self._val(b.get("e_charge_total")),
            "e_discharge_total": self._val(b.get("e_discharge_total")),
            "inv_batt_u": self._val(b.get("inv_batt_u")),
            "inv_batt_i": self._val(b.get("inv_batt_i")),
            "inv_batt_p": self._val(b.get("inv_batt_p")),
            "bms_batt_u": self._val(b.get("bms_batt_u")),
            "bms_batt_i": self._val(b.get("bms_batt_i")),
            "bms_batt_p": self._val(b.get("bms_batt_p")),
            "bms_batt_soc": self._val(b.get("bms_batt_soc")),
            "bms_batt_soh": self._val(b.get("bms_batt_soh")),
            "bms_max_charge_i": self._val(b.get("bms_max_charge_i")),
            "bms_max_discharge_i": self._val(b.get("bms_max_discharge_i")),
            "bms_discharge_volt_limit": self._val(b.get("bms_discharge_volt_limit")),
            "bms_state": b.get("bms_state"),
            "bms_min_cell_volt": self._val(b.get("bms_min_cell_volt")),
            "bms_max_cell_volt": self._val(b.get("bms_max_cell_volt")),
            "bms_min_cell_temp": self._val(b.get("bms_min_cell_temp")),
            "bms_max_cell_temp": self._val(b.get("bms_max_cell_temp")),
            "created_at": ts_now
        }

    def _normalize_payload(self, data: Any) -> Any:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, float): data[k] = round(v, 2)
                elif isinstance(v, (dict, list)): self._normalize_payload(v)
        elif isinstance(data, list):
            for item in data: self._normalize_payload(item)
        return data

    @staticmethod
    def _format_ts(ts: str) -> str:
        if not ts: return datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f") + "+07:00"
        if "T" not in ts: ts = ts.replace(" ", "T")
        if "+" not in ts and not ts.endswith("Z"): ts += "+07:00"
        return ts

    def _normalize_error_items(self, errors: list, payload_created_at: str | None = None) -> list:
        normalized = []
        for item in errors or []:
            if not isinstance(item, dict):
                continue
            normalized.append({
                "fault_code": item.get("fault_code", 0),
                "fault_description": item.get("fault_description", "UNKNOWN"),
                "repair_instruction": item.get("repair_instruction", ""),
                "severity": item.get("severity", "STABLE"),
                "created_at": payload_created_at or self._format_ts(item.get("created_at"))
            })
        return normalized

    def _default_error_item(self, err_row: dict | None, ac_row: dict | None, payload_created_at: str | None = None) -> dict:
        ts = None
        if err_row:
            ts = err_row.get("updated_at")
        if not ts and ac_row:
            ts = ac_row.get("updated_at")
        return {
            "fault_code": 0,
            "fault_description": (err_row or {}).get("status_text") or "UNKNOWN",
            "repair_instruction": "",
            "severity": "STABLE",
            "created_at": payload_created_at or self._format_ts(ts)
        }

    @staticmethod
    def _get_error_severity(err_row: dict | None) -> str:
        if not err_row:
            return ""

        fault_json = err_row.get("fault_json")
        if not fault_json:
            return ""

        try:
            items = json.loads(fault_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""

        if not isinstance(items, list):
            return ""

        for item in items:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "")).strip().upper()
            if severity:
                return severity

        return ""

    @staticmethod
    def _val(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _num(value: Any, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

