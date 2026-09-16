import sqlite3
import json
from typing import List, Dict, Optional
from .base_db import BaseDB

class CacheDB(BaseDB):
    """Quản lý dữ liệu thay đổi nhanh (RAM-based)."""
    
    def __init__(self, db_path: str):
        super().__init__(db_path)
        self.batch_lock = self._lock
    
    def _connect(self):
        conn = super()._connect()
        try:
            conn.execute("PRAGMA synchronous=OFF;")
        except Exception:
            pass
        return conn

    def _create_tables(self):
        with self._connect() as conn:
            # AC Cache
            conn.execute("""
            CREATE TABLE IF NOT EXISTS inverter_ac_cache (
                inverter_id INTEGER PRIMARY KEY, project_id INTEGER,
                IR REAL, Temp_C REAL, P_ac REAL, Q_ac REAL,
                V_a REAL, V_b REAL, V_c REAL, I_a REAL, I_b REAL, I_c REAL,
                PF REAL, H REAL, E_daily REAL, E_total REAL,
                delta_E_monthly REAL DEFAULT 0, E_monthly REAL DEFAULT 0, 
                p_dc_w REAL DEFAULT 0, updated_at TEXT
            );
            """)
            # Migration cache DB cho các cột mới nếu trước đó chưa có
            cols = {row[1] for row in conn.execute("PRAGMA table_info(inverter_ac_cache)").fetchall()}
            if "E_monthly" not in cols:
                conn.execute("ALTER TABLE inverter_ac_cache ADD COLUMN E_monthly REAL DEFAULT 0")
            if "delta_E_monthly" not in cols:
                conn.execute("ALTER TABLE inverter_ac_cache ADD COLUMN delta_E_monthly REAL DEFAULT 0")
            if "p_dc_w" not in cols:
                conn.execute("ALTER TABLE inverter_ac_cache ADD COLUMN p_dc_w REAL DEFAULT 0")

            # MPPT Cache
            conn.execute("""
            CREATE TABLE IF NOT EXISTS mppt_cache (
                inverter_id INTEGER, mppt_index INTEGER, project_id INTEGER,
                V_mppt REAL, I_mppt REAL, P_mppt REAL,
                Max_V REAL DEFAULT 0, Max_I REAL DEFAULT 0, Max_P REAL DEFAULT 0,
                updated_at TEXT, PRIMARY KEY (inverter_id, mppt_index)
            );
            """)
            # Migration MPPT
            cols = {row[1] for row in conn.execute("PRAGMA table_info(mppt_cache)").fetchall()}
            if "Max_V" not in cols:
                conn.execute("ALTER TABLE mppt_cache ADD COLUMN Max_V REAL DEFAULT 0")
            if "Max_I" not in cols:
                conn.execute("ALTER TABLE mppt_cache ADD COLUMN Max_I REAL DEFAULT 0")
            if "Max_P" not in cols:
                conn.execute("ALTER TABLE mppt_cache ADD COLUMN Max_P REAL DEFAULT 0")

            # String Cache
            conn.execute("""
            CREATE TABLE IF NOT EXISTS string_cache (
                inverter_id INTEGER, string_id INTEGER, project_id INTEGER, mppt_id INTEGER,
                I_string REAL, max_I REAL DEFAULT 0, updated_at TEXT,
                PRIMARY KEY (inverter_id, string_id)
            );
            """)
            # Migration String
            cols = {row[1] for row in conn.execute("PRAGMA table_info(string_cache)").fetchall()}
            if "max_I" not in cols:
                conn.execute("ALTER TABLE string_cache ADD COLUMN max_I REAL DEFAULT 0")
            # Error Cache
            conn.execute("""
            CREATE TABLE IF NOT EXISTS error_cache (
                inverter_id INTEGER PRIMARY KEY, project_id INTEGER,
                status_code INTEGER, fault_code INTEGER,
                status_text TEXT, fault_text TEXT, fault_json TEXT, updated_at TEXT
            );
            """)
            # Migration error_cache
            cols = {row[1] for row in conn.execute("PRAGMA table_info(error_cache)").fetchall()}
            if "status_text" not in cols:
                conn.execute("ALTER TABLE error_cache ADD COLUMN status_text TEXT")
            if "fault_text" not in cols:
                conn.execute("ALTER TABLE error_cache ADD COLUMN fault_text TEXT")
            if "fault_json" not in cols:
                conn.execute("ALTER TABLE error_cache ADD COLUMN fault_json TEXT")

            # Meter Cache — Dữ liệu đo lường tại điểm đấu nối lưới
            conn.execute("""
            CREATE TABLE IF NOT EXISTS meter_cache (
                meter_id INTEGER PRIMARY KEY,
                project_id INTEGER,
                P_total REAL, P_a REAL, P_b REAL, P_c REAL,
                Q_total REAL, Q_a REAL, Q_b REAL, Q_c REAL,
                S_total REAL, S_a REAL, S_b REAL, S_c REAL,
                V_a REAL, V_b REAL, V_c REAL, V_phase_avg REAL,
                V_ab REAL, V_bc REAL, V_ca REAL, V_line_avg REAL,
                I_a REAL, I_b REAL, I_c REAL, I_avg REAL,
                PF REAL, PF_a REAL, PF_b REAL, PF_c REAL,
                F REAL,
                exp_st_today REAL, exp_pt_today REAL, exp_qt_today REAL,
                imp_st_today REAL, imp_pt_today REAL, imp_qt_today REAL,
                e_pt_import REAL, e_pt_export REAL,
                e_qt_import REAL, e_qt_export REAL,
                e_st_import REAL, e_st_export REAL,
                updated_at TEXT
            );
            """)

            # Load Cache — Dữ liệu phụ tải / Backup / Smart Load
            conn.execute("""
            CREATE TABLE IF NOT EXISTS load_cache (
                project_id INTEGER PRIMARY KEY,
                e_daily REAL, e_total REAL, p_load REAL,
                e_backup_daily REAL, e_backup_total REAL,
                u_backup_a REAL, u_backup_b REAL, u_backup_c REAL,
                i_backup_a REAL, i_backup_b REAL, i_backup_c REAL,
                p_backup_a REAL, p_backup_b REAL, p_backup_c REAL,
                s_backup_load REAL,
                e_smart_daily REAL, e_smart_total REAL,
                u_smart_a REAL, u_smart_b REAL, u_smart_c REAL,
                i_smart_a REAL, i_smart_b REAL, i_smart_c REAL,
                p_smart_a REAL, p_smart_b REAL, p_smart_c REAL,
                s_smart_load REAL, updated_at TEXT
            );
            """)

            # Battery Cache — Dữ liệu pin lưu trữ / BMS
            conn.execute("""
            CREATE TABLE IF NOT EXISTS battery_cache (
                serial_number TEXT PRIMARY KEY, project_id INTEGER,
                cycle_count REAL, e_charge_daily REAL, e_discharge_daily REAL,
                e_charge_total REAL, e_discharge_total REAL,
                inv_batt_u REAL, inv_batt_i REAL, inv_batt_p REAL,
                bms_batt_u REAL, bms_batt_i REAL, bms_batt_p REAL,
                bms_batt_soc REAL, bms_batt_soh REAL,
                bms_max_charge_i REAL, bms_max_discharge_i REAL,
                bms_discharge_volt_limit REAL, bms_state TEXT,
                bms_min_cell_volt REAL, bms_max_cell_volt REAL,
                bms_min_cell_temp REAL, bms_max_cell_temp REAL,
                updated_at TEXT
            );
            """)


    def get_ac_cache(self, inverter_id: int) -> Optional[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM inverter_ac_cache WHERE inverter_id = ?", (inverter_id,)).fetchone()
                return dict(row) if row else None

    def upsert_inverter_ac(self, inverter_id: int, project_id: int, data: dict):
        from datetime import datetime
        now_str = datetime.now().isoformat()
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO inverter_ac_cache (
                        inverter_id, project_id, IR, Temp_C, P_ac, Q_ac,
                        V_a, V_b, V_c, I_a, I_b, I_c, PF, H,
                        E_daily, E_total, delta_E_monthly, E_monthly, p_dc_w, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(inverter_id) DO UPDATE SET
                        project_id=excluded.project_id, IR=excluded.IR, Temp_C=excluded.Temp_C, P_ac=excluded.P_ac, Q_ac=excluded.Q_ac,
                        V_a=excluded.V_a, V_b=excluded.V_b, V_c=excluded.V_c, I_a=excluded.I_a, I_b=excluded.I_b, I_c=excluded.I_c,
                        PF=excluded.PF, H=excluded.H, E_daily=excluded.E_daily, E_total=excluded.E_total,
                        delta_E_monthly=COALESCE(excluded.delta_E_monthly, inverter_ac_cache.delta_E_monthly),
                        E_monthly=COALESCE(excluded.E_monthly, inverter_ac_cache.E_monthly),
                        p_dc_w=excluded.p_dc_w, updated_at=excluded.updated_at
                """, (inverter_id, project_id, data.get("ir"), data.get("temp_c"), data.get("p_inv_w"), data.get("q_inv_var"),
                      data.get("v_a"), data.get("v_b"), data.get("v_c"), data.get("i_a"), data.get("i_b"), data.get("i_c"),
                      data.get("pf"), data.get("grid_hz"), data.get("e_daily"), data.get("e_total"), data.get("delta_E_monthly"), data.get("e_monthly"),
                      data.get("p_dc_w"), now_str))

    def update_ac_processed(self, inverter_id: int, e_monthly: float, delta_e: float):
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("UPDATE inverter_ac_cache SET E_monthly = ?, delta_E_monthly = ? WHERE inverter_id = ?",
                             (e_monthly, delta_e, inverter_id))

    def get_all_ac_cache(self) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM inverter_ac_cache").fetchall()
                return [dict(r) for r in rows]

    def get_ac_cache_by_project(self, project_id: int) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM inverter_ac_cache WHERE project_id = ?", (project_id,)).fetchall()
                return [dict(r) for r in rows]

    def get_error_cache(self, inverter_id: int) -> Optional[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM error_cache WHERE inverter_id = ?", (inverter_id,)).fetchone()
                return dict(row) if row else None
            
    def upsert_error(self, inverter_id: int, project_id: int, status_code: int, fault_code: int, status_text: str = None, fault_text: str = None, fault_json: str = None):
        from datetime import datetime
        now_str = datetime.now().isoformat()
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO error_cache (inverter_id, project_id, status_code, fault_code, status_text, fault_text, fault_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(inverter_id) DO UPDATE SET
                        project_id=excluded.project_id, status_code=excluded.status_code, fault_code=excluded.fault_code,
                        status_text=COALESCE(excluded.status_text, error_cache.status_text),
                        fault_text=COALESCE(excluded.fault_text, error_cache.fault_text),
                        fault_json=COALESCE(excluded.fault_json, error_cache.fault_json), updated_at=excluded.updated_at
                """, (inverter_id, project_id, status_code, fault_code, status_text, fault_text, fault_json, now_str))

    # --- MPPT ---
    def get_all_mppt_cache(self) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM mppt_cache").fetchall()
                return [dict(r) for r in rows]

    def get_mppt_cache_by_inverter(self, inverter_id: int) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM mppt_cache WHERE inverter_id = ? ORDER BY mppt_index ASC", (inverter_id,)
                ).fetchall()
                return [dict(r) for r in rows]

    def upsert_mppt(self, inverter_id: int, mppt_index: int, project_id: int, data: dict):
        from datetime import datetime
        now_str = datetime.now().isoformat()
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO mppt_cache (inverter_id, mppt_index, project_id, V_mppt, I_mppt, P_mppt, Max_V, Max_I, Max_P, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(inverter_id, mppt_index) DO UPDATE SET
                        project_id=excluded.project_id,
                        V_mppt=excluded.V_mppt, I_mppt=excluded.I_mppt, P_mppt=excluded.P_mppt,
                        Max_V=MAX(excluded.Max_V, mppt_cache.Max_V),
                        Max_I=MAX(excluded.Max_I, mppt_cache.Max_I),
                        Max_P=MAX(excluded.Max_P, mppt_cache.Max_P),
                        updated_at=excluded.updated_at
                """, (inverter_id, mppt_index, project_id,
                      data.get("v_mppt", 0), data.get("i_mppt", 0), data.get("p_mppt", 0),
                      data.get("v_mppt", 0), data.get("i_mppt", 0), data.get("p_mppt", 0),
                      now_str))

    # --- String ---
    def get_all_string_cache(self) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM string_cache").fetchall()
                return [dict(r) for r in rows]

    def get_string_cache_by_inverter(self, inverter_id: int) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM string_cache WHERE inverter_id = ? ORDER BY string_id ASC", (inverter_id,)
                ).fetchall()
                return [dict(r) for r in rows]

    def upsert_string(self, inverter_id: int, string_id: int, project_id: int, mppt_id: int, i_string: float):
        from datetime import datetime
        now_str = datetime.now().isoformat()
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO string_cache (inverter_id, string_id, project_id, mppt_id, I_string, max_I, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(inverter_id, string_id) DO UPDATE SET
                        project_id=excluded.project_id, mppt_id=excluded.mppt_id,
                        I_string=excluded.I_string,
                        max_I=MAX(excluded.I_string, string_cache.max_I),
                        updated_at=excluded.updated_at
                """, (inverter_id, string_id, project_id, mppt_id, i_string, i_string, now_str))

    def reset_mppt_max(self, inverter_id: int):
        """Reset Max values hàng ngày — gọi từ PersistenceWorker khi sang ngày mới."""
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("UPDATE mppt_cache SET Max_V=0, Max_I=0, Max_P=0 WHERE inverter_id=?", (inverter_id,))

    def reset_string_max(self, inverter_id: int):
        """Reset max_I hàng ngày."""
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("UPDATE string_cache SET max_I=0 WHERE inverter_id=?", (inverter_id,))

    def clear_inverter_mppt_string_cache(self, inverter_id: int):
        """Xoá sạch dữ liệu MPPT và String của một inverter trong Cache (trước khi poll mới)."""
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM mppt_cache WHERE inverter_id = ?", (inverter_id,))
                conn.execute("DELETE FROM string_cache WHERE inverter_id = ?", (inverter_id,))

    def update_mppt_max(self, inverter_id: int, mppt_index: int, max_v: float, max_i: float, max_p: float):
        """Cập nhật giá trị Max cho MPPT - dùng để đồng bộ từ RAM MaxTrackingService."""
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("""
                    UPDATE mppt_cache 
                    SET Max_V = ?, Max_I = ?, Max_P = ?
                    WHERE inverter_id = ? AND mppt_index = ?
                """, (max_v, max_i, max_p, inverter_id, mppt_index))

    def update_string_max(self, inverter_id: int, string_id: int, max_i: float):
        """Cập nhật giá trị Max cho String - dùng để đồng bộ từ RAM MaxTrackingService."""
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("""
                    UPDATE string_cache 
                    SET max_I = ?
                    WHERE inverter_id = ? AND string_id = ?
                """, (max_i, inverter_id, string_id))

    # --- Meter Cache ---
    def upsert_meter_cache(self, meter_id: int, project_id: int, data: dict):
        """Cập nhật dữ liệu đo lường Meter vào cache."""
        from datetime import datetime
        now_str = datetime.now().isoformat()
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO meter_cache (
                        meter_id, project_id,
                        P_total, P_a, P_b, P_c,
                        Q_total, Q_a, Q_b, Q_c,
                        S_total, S_a, S_b, S_c,
                        V_a, V_b, V_c, V_phase_avg,
                        V_ab, V_bc, V_ca, V_line_avg,
                        I_a, I_b, I_c, I_avg,
                        PF, PF_a, PF_b, PF_c,
                        F,
                        exp_st_today, exp_pt_today, exp_qt_today,
                        imp_st_today, imp_pt_today, imp_qt_today,
                        e_pt_import, e_pt_export,
                        e_qt_import, e_qt_export,
                        e_st_import, e_st_export,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(meter_id) DO UPDATE SET
                        project_id=excluded.project_id,
                        P_total=excluded.P_total, P_a=excluded.P_a, P_b=excluded.P_b, P_c=excluded.P_c,
                        Q_total=excluded.Q_total, Q_a=excluded.Q_a, Q_b=excluded.Q_b, Q_c=excluded.Q_c,
                        S_total=excluded.S_total, S_a=excluded.S_a, S_b=excluded.S_b, S_c=excluded.S_c,
                        V_a=excluded.V_a, V_b=excluded.V_b, V_c=excluded.V_c, V_phase_avg=excluded.V_phase_avg,
                        V_ab=excluded.V_ab, V_bc=excluded.V_bc, V_ca=excluded.V_ca, V_line_avg=excluded.V_line_avg,
                        I_a=excluded.I_a, I_b=excluded.I_b, I_c=excluded.I_c, I_avg=excluded.I_avg,
                        PF=excluded.PF, PF_a=excluded.PF_a, PF_b=excluded.PF_b, PF_c=excluded.PF_c,
                        F=excluded.F,
                        exp_st_today=excluded.exp_st_today, exp_pt_today=excluded.exp_pt_today, exp_qt_today=excluded.exp_qt_today,
                        imp_st_today=excluded.imp_st_today, imp_pt_today=excluded.imp_pt_today, imp_qt_today=excluded.imp_qt_today,
                        e_pt_import=excluded.e_pt_import, e_pt_export=excluded.e_pt_export,
                        e_qt_import=excluded.e_qt_import, e_qt_export=excluded.e_qt_export,
                        e_st_import=excluded.e_st_import, e_st_export=excluded.e_st_export,
                        updated_at=excluded.updated_at
                """, (
                    meter_id, project_id,
                    data.get("p_total"), data.get("p_a"), data.get("p_b"), data.get("p_c"),
                    data.get("q_total"), data.get("q_a"), data.get("q_b"), data.get("q_c"),
                    data.get("s_total"), data.get("s_a"), data.get("s_b"), data.get("s_c"),
                    data.get("v_a"), data.get("v_b"), data.get("v_c"), data.get("v_phase_avg"),
                    data.get("v_ab"), data.get("v_bc"), data.get("v_ca"), data.get("v_line_avg"),
                    data.get("i_a"), data.get("i_b"), data.get("i_c"), data.get("i_avg"),
                    data.get("pf"), data.get("pf_a"), data.get("pf_b"), data.get("pf_c"),
                    data.get("f"),
                    data.get("exp_st_today"), data.get("exp_pt_today"), data.get("exp_qt_today"),
                    data.get("imp_st_today"), data.get("imp_pt_today"), data.get("imp_qt_today"),
                    data.get("e_pt_import"), data.get("e_pt_export"),
                    data.get("e_qt_import"), data.get("e_qt_export"),
                    data.get("e_st_import"), data.get("e_st_export"),
                    now_str,
                ))

    def get_meter_cache(self, meter_id: int) -> Optional[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM meter_cache WHERE meter_id = ?", (meter_id,)).fetchone()
                return dict(row) if row else None

    def get_meter_cache_by_project(self, project_id: int) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM meter_cache WHERE project_id = ?", (project_id,)).fetchall()
                return [dict(r) for r in rows]

    # --- BATCH COMMIT ---
    def commit_project_batch(self, batch):
        """Lưu toàn bộ dữ liệu AC, MPPT, String, Error của 1 project trong 1 lần giao dịch an toàn."""
        with self.batch_lock:
            for ac_data in batch.ac_data:
                self.upsert_inverter_ac(ac_data["inverter_id"], batch.project_id, ac_data["data"])
            
            for mppt_data in batch.mppt_data:
                self.upsert_mppt(mppt_data["inverter_id"], mppt_data["mppt_index"], batch.project_id, mppt_data["data"])
                
            for string_data in batch.string_data:
                self.upsert_string(string_data["inverter_id"], string_data["string_id"], batch.project_id, string_data["mppt_id"], string_data["i_string"])
                
            for err_data in batch.error_data:
                self.upsert_error(err_data["inverter_id"], batch.project_id, err_data["status_code"], err_data["fault_code"], err_data.get("status_text"), err_data.get("fault_text"), err_data.get("fault_json"))

    # --- Zero Export Status Cache ---
    def upsert_zero_export_status_cache(self, project_id: int, data: dict):
        """Lưu trạng thái runtime của Zero Export vào CacheDB."""
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO zero_export_status_cache (
                        project_id, enabled, suspended_by, p_grid_w,
                        p_inv_total_w, p_inv_setpoint_w, last_action,
                        meter_fail_count, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        enabled=excluded.enabled,
                        suspended_by=excluded.suspended_by,
                        p_grid_w=excluded.p_grid_w,
                        p_inv_total_w=excluded.p_inv_total_w,
                        p_inv_setpoint_w=excluded.p_inv_setpoint_w,
                        last_action=excluded.last_action,
                        meter_fail_count=excluded.meter_fail_count,
                        last_updated=excluded.last_updated
                """, (
                    project_id,
                    1 if data.get("enabled") else 0,
                    data.get("suspended_by"),
                    data.get("p_grid_w"),
                    data.get("p_inv_total_w"),
                    data.get("p_inv_setpoint_w"),
                    data.get("last_action"),
                    data.get("meter_fail_count", 0),
                    data.get("last_updated"),
                ))

    def get_zero_export_status_cache(self, project_id: int) -> Optional[dict]:
        """Đọc trạng thái runtime của Zero Export từ CacheDB."""
        with self.batch_lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM zero_export_status_cache WHERE project_id = ?", (project_id,)).fetchone()
                if not row:
                    return None
                res = dict(row)
                res["enabled"] = bool(res["enabled"])
                return res

    # --- Load Cache ---
    def upsert_load_cache(self, project_id: int, data: dict):
        from datetime import datetime
        now_str = datetime.now().isoformat()
        with self.batch_lock:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO load_cache (
                        project_id, e_daily, e_total, p_load,
                        e_backup_daily, e_backup_total,
                        u_backup_a, u_backup_b, u_backup_c,
                        i_backup_a, i_backup_b, i_backup_c,
                        p_backup_a, p_backup_b, p_backup_c,
                        s_backup_load,
                        e_smart_daily, e_smart_total,
                        u_smart_a, u_smart_b, u_smart_c,
                        i_smart_a, i_smart_b, i_smart_c,
                        p_smart_a, p_smart_b, p_smart_c,
                        s_smart_load, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        e_daily=excluded.e_daily, e_total=excluded.e_total, p_load=excluded.p_load,
                        e_backup_daily=excluded.e_backup_daily, e_backup_total=excluded.e_backup_total,
                        u_backup_a=excluded.u_backup_a, u_backup_b=excluded.u_backup_b, u_backup_c=excluded.u_backup_c,
                        i_backup_a=excluded.i_backup_a, i_backup_b=excluded.i_backup_b, i_backup_c=excluded.i_backup_c,
                        p_backup_a=excluded.p_backup_a, p_backup_b=excluded.p_backup_b, p_backup_c=excluded.p_backup_c,
                        s_backup_load=excluded.s_backup_load,
                        e_smart_daily=excluded.e_smart_daily, e_smart_total=excluded.e_smart_total,
                        u_smart_a=excluded.u_smart_a, u_smart_b=excluded.u_smart_b, u_smart_c=excluded.u_smart_c,
                        i_smart_a=excluded.i_smart_a, i_smart_b=excluded.i_smart_b, i_smart_c=excluded.i_smart_c,
                        p_smart_a=excluded.p_smart_a, p_smart_b=excluded.p_smart_b, p_smart_c=excluded.p_smart_c,
                        s_smart_load=excluded.s_smart_load, updated_at=excluded.updated_at
                """, (
                    project_id, data.get("e_daily"), data.get("e_total"), data.get("p_load"),
                    data.get("e_backup_daily"), data.get("e_backup_total"),
                    data.get("u_backup_a"), data.get("u_backup_b"), data.get("u_backup_c"),
                    data.get("i_backup_a"), data.get("i_backup_b"), data.get("i_backup_c"),
                    data.get("p_backup_a"), data.get("p_backup_b"), data.get("p_backup_c"),
                    data.get("s_backup_load"),
                    data.get("e_smart_daily"), data.get("e_smart_total"),
                    data.get("u_smart_a"), data.get("u_smart_b"), data.get("u_smart_c"),
                    data.get("i_smart_a"), data.get("i_smart_b"), data.get("i_smart_c"),
                    data.get("p_smart_a"), data.get("p_smart_b"), data.get("p_smart_c"),
                    data.get("s_smart_load"), now_str
                ))

    def get_load_cache_by_project(self, project_id: int) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM load_cache WHERE project_id = ?", (project_id,)).fetchall()
                return [dict(r) for r in rows]

    # --- Battery Cache ---
    def upsert_battery_cache(self, project_id: int, batteries: List[dict]):
        from datetime import datetime
        now_str = datetime.now().isoformat()
        with self.batch_lock:
            with self._connect() as conn:
                for b in batteries or []:
                    sn = b.get("serial_number")
                    if not sn: continue
                    conn.execute("""
                        INSERT INTO battery_cache (
                            serial_number, project_id, cycle_count,
                            e_charge_daily, e_discharge_daily,
                            e_charge_total, e_discharge_total,
                            inv_batt_u, inv_batt_i, inv_batt_p,
                            bms_batt_u, bms_batt_i, bms_batt_p,
                            bms_batt_soc, bms_batt_soh,
                            bms_max_charge_i, bms_max_discharge_i,
                            bms_discharge_volt_limit, bms_state,
                            bms_min_cell_volt, bms_max_cell_volt,
                            bms_min_cell_temp, bms_max_cell_temp,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(serial_number) DO UPDATE SET
                            project_id=excluded.project_id, cycle_count=excluded.cycle_count,
                            e_charge_daily=excluded.e_charge_daily, e_discharge_daily=excluded.e_discharge_daily,
                            e_charge_total=excluded.e_charge_total, e_discharge_total=excluded.e_discharge_total,
                            inv_batt_u=excluded.inv_batt_u, inv_batt_i=excluded.inv_batt_i, inv_batt_p=excluded.inv_batt_p,
                            bms_batt_u=excluded.bms_batt_u, bms_batt_i=excluded.bms_batt_i, bms_batt_p=excluded.bms_batt_p,
                            bms_batt_soc=excluded.bms_batt_soc, bms_batt_soh=excluded.bms_batt_soh,
                            bms_max_charge_i=excluded.bms_max_charge_i, bms_max_discharge_i=excluded.bms_max_discharge_i,
                            bms_discharge_volt_limit=excluded.bms_discharge_volt_limit, bms_state=excluded.bms_state,
                            bms_min_cell_volt=excluded.bms_min_cell_volt, bms_max_cell_volt=excluded.bms_max_cell_volt,
                            bms_min_cell_temp=excluded.bms_min_cell_temp, bms_max_cell_temp=excluded.bms_max_cell_temp,
                            updated_at=excluded.updated_at
                    """, (
                        sn, project_id, b.get("cycle_count"),
                        b.get("e_charge_daily"), b.get("e_discharge_daily"),
                        b.get("e_charge_total"), b.get("e_discharge_total"),
                        b.get("inv_batt_u"), b.get("inv_batt_i"), b.get("inv_batt_p"),
                        b.get("bms_batt_u"), b.get("bms_batt_i"), b.get("bms_batt_p"),
                        b.get("bms_batt_soc"), b.get("bms_batt_soh"),
                        b.get("bms_max_charge_i"), b.get("bms_max_discharge_i"),
                        b.get("bms_discharge_volt_limit"), b.get("bms_state"),
                        b.get("bms_min_cell_volt"), b.get("bms_max_cell_volt"),
                        b.get("bms_min_cell_temp"), b.get("bms_max_cell_temp"),
                        now_str
                    ))

    def get_battery_cache_by_project(self, project_id: int) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM battery_cache WHERE project_id = ?", (project_id,)).fetchall()
                return [dict(r) for r in rows]

    def get_all_battery_cache(self) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM battery_cache").fetchall()
                return [dict(r) for r in rows]

    def get_all_load_cache(self) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM load_cache").fetchall()
                return [dict(r) for r in rows]

    def get_all_meter_cache(self) -> List[dict]:
        with self.batch_lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM meter_cache").fetchall()
                return [dict(r) for r in rows]

