import sqlite3
import json
from typing import Optional, List
from dataclasses import asdict
from .base_db import BaseDB, to_dataclass

from backend.models.realtime import (
    ProjectRealtimeCreate, ProjectRealtimeResponse,
    InverterACRealtimeCreate, InverterACRealtimeResponse,
    InverterErrorCreate, InverterErrorResponse,
    mpptRealtimeCreate, mpptRealtimeResponse,
    stringRealtimeCreate, stringRealtimeResponse,
    BatteryRealtimeCreate, BatteryRealtimeResponse,
    LoadRealtimeCreate, LoadRealtimeResponse,
    MeterRealtimeCreate, MeterRealtimeResponse
)
from backend.models.schedule import (
    ControlScheduleCreate, ControlScheduleUpdate, ControlScheduleResponse
)

class RealtimeDB(BaseDB):
    """Quản lý dữ liệu Snapshot ghi xuống Disk (RealtimeDB)."""
    
    def _connect(self):
        conn = super()._connect()
        try:
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA cache_size = -2000;")  # Tận dụng 2MB RAM cache để hạn chế tối đa I/O đọc đĩa
        except Exception:
            pass
        return conn

    def _create_tables(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            # Uploader Outbox
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS uploader_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                server_id INTEGER,
                data_type TEXT DEFAULT 'Project',
                data_json TEXT,
                created_at TEXT
            );
            """)
            # Migration uploader_outbox
            cols = {row[1] for row in conn.execute("PRAGMA table_info(uploader_outbox)").fetchall()}
            if "server_id" not in cols:
                conn.execute("ALTER TABLE uploader_outbox ADD COLUMN server_id INTEGER")
            if "data_type" not in cols:
                conn.execute("ALTER TABLE uploader_outbox ADD COLUMN data_type TEXT DEFAULT 'Project'")
            # Project Realtime
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_realtime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER, Temp_C REAL, P_ac REAL, P_dc REAL,
                E_daily REAL, delta_E_monthly REAL, E_monthly REAL, E_total REAL,
                severity TEXT, created_at TEXT
            );
            """)
            # Inverter AC Realtime
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS inverter_ac_realtime (
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, inverter_id INTEGER,
                IR REAL, Temp_C REAL, P_ac REAL, Q_ac REAL,
                V_a REAL, V_b REAL, V_c REAL, I_a REAL, I_b REAL, I_c REAL,
                PF REAL, H REAL, E_daily REAL, delta_E_monthly REAL, E_monthly REAL, E_total REAL,
                created_at TEXT
            );
            """)
            # Errors
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS inverter_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER, inverter_id INTEGER, fault_code INTEGER,
                fault_description TEXT, repair_instruction TEXT, severity TEXT, created_at TEXT
            );
            """)
            # MPPT & String Realtime tables
            cursor.execute("CREATE TABLE IF NOT EXISTS mppt_realtime (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, inverter_id INTEGER, mppt_index INTEGER, string_on_mppt INTEGER, V_mppt REAL, I_mppt REAL, P_mppt REAL, Max_I REAL, Max_V REAL, Max_P REAL, created_at TEXT);")
            cursor.execute("CREATE TABLE IF NOT EXISTS string_realtime (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, inverter_id INTEGER, mppt_id INTEGER, string_id INTEGER, I_string REAL, max_I REAL, created_at TEXT);")

            # Battery Realtime table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS battery_realtime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER, inverter_id INTEGER, battery_id INTEGER, serial_number TEXT,
                inv_batt_u REAL, inv_batt_i REAL, inv_batt_p REAL,
                bms_batt_u REAL, bms_batt_i REAL, bms_batt_p REAL,
                bms_batt_soc REAL, bms_batt_soh REAL, batt_direction INTEGER,
                e_charge_daily REAL, e_discharge_daily REAL, e_charge_total REAL, e_discharge_total REAL,
                bms_min_cell_temp REAL, bms_max_cell_temp REAL, bms_min_cell_volt REAL, bms_max_cell_volt REAL,
                created_at TEXT
            );
            """)

            # Load Realtime table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS load_realtime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER, inverter_id INTEGER,
                p_load REAL, s_backup_load REAL,
                u_backup_a REAL, u_backup_b REAL, u_backup_c REAL,
                i_backup_a REAL, i_backup_b REAL, i_backup_c REAL,
                p_backup_a REAL, p_backup_b REAL, p_backup_c REAL,
                e_daily REAL, e_total REAL, e_backup_daily REAL, e_backup_total REAL,
                created_at TEXT
            );
            """)

            # Meter Realtime table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS meter_realtime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER, meter_id INTEGER, serial_number TEXT,
                u_a REAL, u_b REAL, u_c REAL, i_a REAL, i_b REAL, i_c REAL,
                p_a REAL, p_b REAL, p_c REAL, P_total REAL, Q_total REAL, S_total REAL,
                PF REAL, f REAL, imp_pt_today REAL, exp_pt_today REAL, imp_pt_total REAL, exp_pt_total REAL,
                created_at TEXT
            );
            """)

            # Control Schedules
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS control_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                project_name TEXT,
                scope TEXT,
                inverter_index INTEGER,
                inverter_id INTEGER,
                serial_number TEXT,
                mode TEXT,
                limit_watts REAL,
                limit_percent REAL,
                start_at TEXT,
                end_at TEXT,
                status TEXT DEFAULT 'SCHEDULED',
                hours REAL,
                day TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            );
            """)
            cols_sched = {row[1] for row in conn.execute("PRAGMA table_info(control_schedules)").fetchall()}
            if "project_name" not in cols_sched:
                conn.execute("ALTER TABLE control_schedules ADD COLUMN project_name TEXT")
            if "inverter_id" not in cols_sched:
                conn.execute("ALTER TABLE control_schedules ADD COLUMN inverter_id INTEGER")
            if "serial_number" not in cols_sched:
                conn.execute("ALTER TABLE control_schedules ADD COLUMN serial_number TEXT")
            if "hours" not in cols_sched:
                conn.execute("ALTER TABLE control_schedules ADD COLUMN hours REAL")
            if "day" not in cols_sched:
                conn.execute("ALTER TABLE control_schedules ADD COLUMN day TEXT")
            if "updated_at" not in cols_sched:
                conn.execute("ALTER TABLE control_schedules ADD COLUMN updated_at TEXT")

            # EVN Control Commands (giao tiếp giữa container EVN → Polling)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS evn_control_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                axis TEXT NOT NULL,        -- 'P' hoặc 'Q'
                mode TEXT NOT NULL,        -- 'KW', 'KVAR', 'PERCENT', 'RESET'
                value REAL DEFAULT 0.0,
                status TEXT DEFAULT 'PENDING',  -- 'PENDING', 'DONE'
                created_at TEXT
            );
            """)

            # --- Migration: project_realtime ---
            cols_proj = {row[1] for row in conn.execute("PRAGMA table_info(project_realtime)").fetchall()}
            if "delta_E_monthly" not in cols_proj:
                conn.execute("ALTER TABLE project_realtime ADD COLUMN delta_E_monthly REAL DEFAULT 0")
                if "denta_E_monthly" in cols_proj:
                    conn.execute("UPDATE project_realtime SET delta_E_monthly = denta_E_monthly")

            # --- Migration: inverter_ac_realtime ---
            cols_ac = {row[1] for row in conn.execute("PRAGMA table_info(inverter_ac_realtime)").fetchall()}
            if "delta_E_monthly" not in cols_ac:
                conn.execute("ALTER TABLE inverter_ac_realtime ADD COLUMN delta_E_monthly REAL DEFAULT 0")
                if "denta_E_monthly" in cols_ac:
                    conn.execute("UPDATE inverter_ac_realtime SET delta_E_monthly = denta_E_monthly")

            # --- Indexes ---
            # Mục đích: tăng tốc độ tất cả query SELECT trên các bảng lớn.
            # CREATE INDEX IF NOT EXISTS là idempotent — an toàn khi chạy nhiều lần.
            # Nếu DB đang bị lock (hiếm), bỏ qua và log cảnh báo — không crash service.
            try:
                # inverter_ac_realtime — bảng lớn nhất, cần 2 index
                # Phục vụ: get_latest_inverter_ac_realtime(), get_inverter_ac_range(),
                #          energy_service.py raw SQL (SUM delta_E_monthly WHERE inverter_id + created_at)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_inv_ac_inv_time
                    ON inverter_ac_realtime(inverter_id, created_at DESC)
                """)
                # Phục vụ: get_latest_ac_batch(), get_yesterday_energy_by_project()
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_inv_ac_proj_time
                    ON inverter_ac_realtime(project_id, created_at DESC)
                """)

                # project_realtime — phục vụ dashboard và chart lịch sử
                # Phục vụ: get_latest_project_realtime(), get_project_realtime_range()
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_proj_rt_proj_time
                    ON project_realtime(project_id, created_at DESC)
                """)

                # inverter_errors — phục vụ trang lịch sử lỗi
                # Phục vụ: get_inverter_errors()
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_inv_err_inv_time
                    ON inverter_errors(inverter_id, created_at DESC)
                """)

                # mppt_realtime — bảng lớn (N_inverter × N_mppt × 288/ngày)
                # Phục vụ: get_latest_mppt_batch(), max_tracking_service seed
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mppt_rt_inv_idx
                    ON mppt_realtime(inverter_id, mppt_index)
                """)

                # string_realtime — phục vụ trang chi tiết string
                # Phục vụ: get_latest_string_batch(), max_tracking_service seed
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_str_rt_inv_sid
                    ON string_realtime(inverter_id, string_id)
                """)

                # battery_realtime
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_batt_rt_proj_time
                    ON battery_realtime(project_id, created_at DESC)
                """)

                # load_realtime
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_load_rt_proj_time
                    ON load_realtime(project_id, created_at DESC)
                """)

                # meter_realtime
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_meter_rt_proj_time
                    ON meter_realtime(project_id, created_at DESC)
                """)

            except Exception as idx_err:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    f"RealtimeDB: Could not create indexes (non-critical, will retry on next startup): {idx_err}"
                )


    # --- Outbox API ---
    def post_to_outbox(self, project_id: int, server_id: int, data: dict, data_type: str = "Project"):
        from datetime import datetime
        now_str = datetime.now().isoformat()
        with self._connect() as conn:
            if data_type == "Project":
                conn.execute(
                    "DELETE FROM uploader_outbox WHERE project_id = ? AND data_type = 'Project'",
                    (project_id,)
                )
            conn.execute("INSERT INTO uploader_outbox (project_id, server_id, data_type, data_json, created_at) VALUES (?, ?, ?, ?, ?)",
                         (project_id, server_id, data_type, json.dumps(data), now_str))

    def get_all_outbox(self) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, project_id, server_id, data_type, data_json, created_at FROM uploader_outbox").fetchall()
            result = []
            for r in rows:
                d = json.loads(r["data_json"])
                d["id"] = r["id"]
                d["project_id"] = r["project_id"]
                d["server_id"] = r["server_id"]
                d["data_type"] = r["data_type"]
                result.append(d)
            return result

    def delete_from_outbox(self, record_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM uploader_outbox WHERE id=?", (record_id,))

    def trim_outbox(self, max_rows: int):
        """Giới hạn số lượng bản ghi trong outbox để tránh đầy ổ đĩa."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM uploader_outbox").fetchone()[0]
            if count > max_rows:
                to_delete = count - max_rows
                # Lấy ID của các bản ghi cũ nhất
                old_ids = conn.execute(
                    "SELECT id FROM uploader_outbox ORDER BY id ASC LIMIT ?", (to_delete,)
                ).fetchall()
                ids = [r[0] for r in old_ids]
                if ids:
                    placeholders = ",".join("?" * len(ids))
                    conn.execute(f"DELETE FROM uploader_outbox WHERE id IN ({placeholders})", ids)

    # --- EVN Control Commands API ---
    def push_evn_command(self, project_id: int, axis: str, mode: str, value: float = 0.0):
        """
        Ghi lệnh điều khiển EVN vào DB để container Polling thực hiện.
        Args:
            project_id: ID của project cần điều khiển.
            axis: 'P' hoặc 'Q'.
            mode: 'KW', 'KVAR', 'PERCENT', hoặc 'RESET'.
            value: Giá trị điều khiển (0.0 nếu RESET).
        """
        from datetime import datetime
        now_str = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO evn_control_commands (project_id, axis, mode, value, status, created_at) VALUES (?, ?, ?, ?, 'PENDING', ?)",
                (project_id, axis, mode, value, now_str)
            )

    def get_pending_evn_commands(self) -> List[dict]:
        """Lấy tất cả lệnh EVN đang chờ thực hiện (status=PENDING)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, project_id, axis, mode, value, created_at FROM evn_control_commands WHERE status='PENDING' ORDER BY id ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_evn_command_done(self, command_id: int):
        """Đánh dấu lệnh EVN đã được thực hiện xong."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE evn_control_commands SET status='DONE' WHERE id=?",
                (command_id,)
            )

    def clear_old_evn_commands(self, keep_hours: int = 24):
        """Xóa các lệnh EVN cũ hơn N giờ để tránh đầy DB."""
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=keep_hours)).isoformat()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM evn_control_commands WHERE status='DONE' AND created_at < ?",
                (cutoff,)
            )

    # --- History API ---
    def post_inverter_error(self, data: InverterErrorCreate):
        d = asdict(data)
        with self._connect() as conn:
            conn.execute("INSERT INTO inverter_errors (project_id, inverter_id, fault_code, fault_description, repair_instruction, severity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (d["project_id"], d["inverter_id"], d["fault_code"], d["fault_description"], d["repair_instruction"], d["severity"], d["created_at"]))

    def post_inverter_ac_batch(self, records: List[InverterACRealtimeCreate]):
        if not records: return
        values = [(r.project_id, r.inverter_id, r.IR, r.Temp_C, r.P_ac, r.Q_ac, r.V_a, r.V_b, r.V_c, r.I_a, r.I_b, r.I_c, r.PF, r.H, r.E_daily, r.delta_E_monthly, r.E_monthly, r.E_total, r.created_at) for r in records]
        with self._connect() as conn:
            conn.executemany("INSERT INTO inverter_ac_realtime (project_id, inverter_id, IR, Temp_C, P_ac, Q_ac, V_a, V_b, V_c, I_a, I_b, I_c, PF, H, E_daily, delta_E_monthly, E_monthly, E_total, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)

    def get_latest_inverter_ac_realtime(self, inverter_id: int) -> Optional[InverterACRealtimeResponse]:
        """Lấy bản ghi AC realtime mới nhất của inverter từ Disk (dùng khi seed EnergyService)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM inverter_ac_realtime WHERE inverter_id = ? ORDER BY created_at DESC LIMIT 1",
                (inverter_id,)
            ).fetchone()
            return to_dataclass(InverterACRealtimeResponse, row)

    def get_latest_ac_batch(self, project_id: int) -> List[InverterACRealtimeResponse]:
        """Lấy bản ghi AC realtime mới nhất của mỗi inverter trong một project."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM inverter_ac_realtime
                WHERE id IN (
                    SELECT MAX(id) FROM inverter_ac_realtime
                    WHERE project_id = ?
                    GROUP BY inverter_id
                )
            """, (project_id,)).fetchall()
            return [to_dataclass(InverterACRealtimeResponse, r) for r in rows]

    # --- MPPT Realtime API ---
    def get_latest_mppt_batch(self, inverter_id: int) -> List[mpptRealtimeResponse]:
        """Lấy danh sách điểm MPPT mới nhất của 1 inverter từ Disk (dùng khi seed)."""
        with self._connect() as conn:
            # Lấy bản ghi có created_at mới nhất cho inverter này
            rows = conn.execute("""
                SELECT * FROM mppt_realtime
                WHERE id IN (
                    SELECT MAX(id) FROM mppt_realtime 
                    WHERE inverter_id = ?
                    GROUP BY mppt_index
                )
            """, (inverter_id,)).fetchall()
            return [to_dataclass(mpptRealtimeResponse, r) for r in rows]

    def get_inverter_errors(self, inverter_id: int) -> List[InverterErrorResponse]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM inverter_errors WHERE inverter_id = ? ORDER BY created_at DESC",
                (inverter_id,)
            ).fetchall()
            return [to_dataclass(InverterErrorResponse, r) for r in rows]

    def post_mppt_batch(self, records: List[mpptRealtimeCreate]):
        if not records: return
        values = [(r.project_id, r.inverter_id, r.mppt_index, r.string_on_mppt, r.V_mppt, r.I_mppt, r.P_mppt, r.Max_I, r.Max_V, r.Max_P, r.created_at) for r in records]
        with self._connect() as conn:
            conn.executemany("INSERT INTO mppt_realtime (project_id, inverter_id, mppt_index, string_on_mppt, V_mppt, I_mppt, P_mppt, Max_I, Max_V, Max_P, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", values)

    # --- String Realtime API ---
    def get_latest_string_batch(self, inverter_id: int) -> List[stringRealtimeResponse]:
        """Lấy danh sách điểm String mới nhất của 1 inverter từ Disk (dùng khi seed)."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM string_realtime
                WHERE id IN (
                    SELECT MAX(id) FROM string_realtime 
                    WHERE inverter_id = ?
                    GROUP BY string_id
                )
            """, (inverter_id,)).fetchall()
            return [to_dataclass(stringRealtimeResponse, r) for r in rows]

    def post_string_batch(self, records: List[stringRealtimeCreate]):
        if not records: return
        values = [(r.project_id, r.inverter_id, r.mppt_id, r.string_id, r.I_string, r.max_I, r.created_at) for r in records]
        with self._connect() as conn:
            conn.executemany("INSERT INTO string_realtime (project_id, inverter_id, mppt_id, string_id, I_string, max_I, created_at) VALUES (?,?,?,?,?,?,?)", values)

    # --- Project Realtime API ---
    def post_project_realtime(self, data: ProjectRealtimeCreate):
        d = asdict(data)
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO project_realtime (
                    project_id, Temp_C, P_ac, P_dc, E_daily, delta_E_monthly, E_monthly, E_total, severity, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (d["project_id"], d["Temp_C"], d["P_ac"], d["P_dc"], d["E_daily"], d["delta_E_monthly"], d["E_monthly"], d["E_total"], d["severity"], d["created_at"]))

    def get_latest_project_realtime(self, project_id: int) -> Optional[ProjectRealtimeResponse]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM project_realtime WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,)
            ).fetchone()
            return to_dataclass(ProjectRealtimeResponse, row)

    def get_project_realtime_range(self, project_id: int, start: str, end: str) -> List[ProjectRealtimeResponse]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_realtime WHERE project_id = ? AND created_at BETWEEN ? AND ? ORDER BY created_at ASC",
                (project_id, start, end)
            ).fetchall()
            return [to_dataclass(ProjectRealtimeResponse, r) for r in rows]

    def get_inverter_ac_range(self, inverter_id: int, start: str, end: str) -> List[InverterACRealtimeResponse]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM inverter_ac_realtime WHERE inverter_id = ? AND created_at BETWEEN ? AND ? ORDER BY created_at ASC",
                (inverter_id, start, end)
            ).fetchall()
            return [to_dataclass(InverterACRealtimeResponse, r) for r in rows]

    # --- Control Schedule API ---
    def get_schedule(self, schedule_id: int) -> Optional[ControlScheduleResponse]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM control_schedules WHERE id=?", (schedule_id,)).fetchone()
            return to_dataclass(ControlScheduleResponse, row)

    def get_all_schedules(self) -> List[ControlScheduleResponse]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM control_schedules ORDER BY start_at ASC").fetchall()
            return [to_dataclass(ControlScheduleResponse, r) for r in rows]

    def upsert_schedule(self, data: ControlScheduleCreate, schedule_id: Optional[int] = None) -> ControlScheduleResponse:
        data_dict = asdict(data)
        with self._connect() as conn:
            cursor = conn.cursor()
            if schedule_id:
                existing = conn.execute(
                    "SELECT 1 FROM control_schedules WHERE id=?",
                    (schedule_id,),
                ).fetchone()
                if existing:
                    fields = []
                    values = []
                    for k, v in data_dict.items():
                        if v is not None:
                            fields.append(f"{k} = ?")
                            values.append(v)
                    if not fields:
                        return self.get_schedule(schedule_id)
                    values.append(schedule_id)
                    cursor.execute(f"UPDATE control_schedules SET {', '.join(fields)} WHERE id=?", tuple(values))
                    final_id = schedule_id
                else:
                    insert_dict = {"id": schedule_id, **data_dict}
                    keys = [k for k, v in insert_dict.items() if v is not None]
                    placeholders = ["?" for _ in keys]
                    values = [insert_dict[k] for k in keys]
                    cursor.execute(
                        f"INSERT INTO control_schedules ({', '.join(keys)}) VALUES ({', '.join(placeholders)})",
                        tuple(values),
                    )
                    final_id = schedule_id
            else:
                keys = [k for k, v in data_dict.items() if v is not None]
                placeholders = ["?" for _ in keys]
                values = [data_dict[k] for k in keys]
                cursor.execute(f"INSERT INTO control_schedules ({', '.join(keys)}) VALUES ({', '.join(placeholders)})", tuple(values))
                final_id = cursor.lastrowid
            
            row = conn.execute("SELECT * FROM control_schedules WHERE id=?", (final_id,)).fetchone()
            return to_dataclass(ControlScheduleResponse, row)

    def patch_schedule(self, schedule_id: int, data: ControlScheduleUpdate):
        data_dict = asdict(data)
        fields = [f"{k} = ?" for k, v in data_dict.items() if v is not None]
        values = [v for v in data_dict.values() if v is not None]
        if not fields: return
        values.append(schedule_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE control_schedules SET {', '.join(fields)} WHERE id=?", tuple(values))

    def delete_schedule(self, schedule_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM control_schedules WHERE id=?", (schedule_id,))

    def delete_inverter_data(self, inverter_id: int):
        """Xóa toàn bộ dữ liệu lịch sử liên quan đến 1 inverter."""
        with self._connect() as conn:
            conn.execute("DELETE FROM inverter_ac_realtime WHERE inverter_id=?", (inverter_id,))
            conn.execute("DELETE FROM inverter_errors WHERE inverter_id=?", (inverter_id,))
            conn.execute("DELETE FROM mppt_realtime WHERE inverter_id=?", (inverter_id,))
            conn.execute("DELETE FROM string_realtime WHERE inverter_id=?", (inverter_id,))
            conn.execute("DELETE FROM control_schedules WHERE inverter_id=?", (inverter_id,))

    def delete_project_data(self, project_id: int):
        """Xóa dữ liệu cấp độ project (outbox, realtime summary, schedules, battery, load, meter)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM project_realtime WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM battery_realtime WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM load_realtime WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM meter_realtime WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM uploader_outbox WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM control_schedules WHERE project_id=?", (project_id,))

    def purge_old_data(self, days: int):
        """Xóa dữ liệu lịch sử cũ hơn N ngày để giải phóng bộ nhớ."""
        if days <= 0:
            return
            
        from datetime import datetime, timedelta
        import logging
        logger = logging.getLogger(__name__)
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        logger.info(f"RealtimeDB: Purging data older than {cutoff_date} ({days} days)...")
        
        tables = [
            "project_realtime", 
            "inverter_ac_realtime", 
            "inverter_errors", 
            "mppt_realtime", 
            "string_realtime",
            "battery_realtime",
            "load_realtime",
            "meter_realtime"
        ]

    # --- Battery Realtime API ---
    def post_battery_batch(self, records: List[BatteryRealtimeCreate]):
        if not records: return
        values = [(
            r.project_id, r.inverter_id, r.battery_id, r.serial_number,
            r.inv_batt_u, r.inv_batt_i, r.inv_batt_p,
            r.bms_batt_u, r.bms_batt_i, r.bms_batt_p,
            r.bms_batt_soc, r.bms_batt_soh, r.batt_direction,
            r.e_charge_daily, r.e_discharge_daily, r.e_charge_total, r.e_discharge_total,
            r.bms_min_cell_temp, r.bms_max_cell_temp, r.bms_min_cell_volt, r.bms_max_cell_volt,
            r.created_at
        ) for r in records]
        with self._connect() as conn:
            conn.executemany("""
                INSERT INTO battery_realtime (
                    project_id, inverter_id, battery_id, serial_number,
                    inv_batt_u, inv_batt_i, inv_batt_p,
                    bms_batt_u, bms_batt_i, bms_batt_p,
                    bms_batt_soc, bms_batt_soh, batt_direction,
                    e_charge_daily, e_discharge_daily, e_charge_total, e_discharge_total,
                    bms_min_cell_temp, bms_max_cell_temp, bms_min_cell_volt, bms_max_cell_volt,
                    created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, values)

    def get_latest_battery_batch(self, project_id: int) -> List[BatteryRealtimeResponse]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM battery_realtime
                WHERE id IN (
                    SELECT MAX(id) FROM battery_realtime
                    WHERE project_id = ?
                    GROUP BY COALESCE(battery_id, inverter_id, 0)
                )
            """, (project_id,)).fetchall()
            return [to_dataclass(BatteryRealtimeResponse, r) for r in rows]

    # --- Load Realtime API ---
    def post_load_batch(self, records: List[LoadRealtimeCreate]):
        if not records: return
        values = [(
            r.project_id, r.inverter_id, r.p_load, r.s_backup_load,
            r.u_backup_a, r.u_backup_b, r.u_backup_c,
            r.i_backup_a, r.i_backup_b, r.i_backup_c,
            r.p_backup_a, r.p_backup_b, r.p_backup_c,
            r.e_daily, r.e_total, r.e_backup_daily, r.e_backup_total,
            r.created_at
        ) for r in records]
        with self._connect() as conn:
            conn.executemany("""
                INSERT INTO load_realtime (
                    project_id, inverter_id, p_load, s_backup_load,
                    u_backup_a, u_backup_b, u_backup_c,
                    i_backup_a, i_backup_b, i_backup_c,
                    p_backup_a, p_backup_b, p_backup_c,
                    e_daily, e_total, e_backup_daily, e_backup_total,
                    created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, values)

    def get_latest_load_batch(self, project_id: int) -> List[LoadRealtimeResponse]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM load_realtime
                WHERE id IN (
                    SELECT MAX(id) FROM load_realtime
                    WHERE project_id = ?
                    GROUP BY COALESCE(inverter_id, 0)
                )
            """, (project_id,)).fetchall()
            return [to_dataclass(LoadRealtimeResponse, r) for r in rows]

    # --- Meter (Grid) Realtime API ---
    def post_meter_batch(self, records: List[MeterRealtimeCreate]):
        if not records: return
        values = [(
            r.project_id, r.meter_id, r.serial_number,
            r.u_a, r.u_b, r.u_c, r.i_a, r.i_b, r.i_c,
            r.p_a, r.p_b, r.p_c, r.P_total, r.Q_total, r.S_total,
            r.PF, r.f, r.imp_pt_today, r.exp_pt_today, r.imp_pt_total, r.exp_pt_total,
            r.created_at
        ) for r in records]
        with self._connect() as conn:
            conn.executemany("""
                INSERT INTO meter_realtime (
                    project_id, meter_id, serial_number,
                    u_a, u_b, u_c, i_a, i_b, i_c,
                    p_a, p_b, p_c, P_total, Q_total, S_total,
                    PF, f, imp_pt_today, exp_pt_today, imp_pt_total, exp_pt_total,
                    created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, values)

    def get_latest_meter_batch(self, project_id: int) -> List[MeterRealtimeResponse]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM meter_realtime
                WHERE id IN (
                    SELECT MAX(id) FROM meter_realtime
                    WHERE project_id = ?
                    GROUP BY COALESCE(meter_id, 0)
                )
            """, (project_id,)).fetchall()
            return [to_dataclass(MeterRealtimeResponse, r) for r in rows]
        
        try:
            with self._connect() as conn:
                total_deleted = 0
                for table in tables:
                    cursor = conn.execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff_date,))
                    total_deleted += cursor.rowcount
                
                if total_deleted > 0:
                    logger.info(f"RealtimeDB: Deleted {total_deleted} old records successfully.")
                else:
                    logger.info("RealtimeDB: No old records found to purge.")
        except Exception as e:
            logger.error(f"RealtimeDB: Error during purge: {e}")

    # --- Yesterday Energy (D-1) ---
    def get_yesterday_energy_by_inverter(self, inverter_id: int) -> float:
        """Lấy E_daily từ record CUỐI CÙNG của ngày hôm qua."""
        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with self._connect() as conn:
            row = conn.execute("""
                SELECT E_daily FROM inverter_ac_realtime
                WHERE inverter_id = ? AND created_at LIKE ?
                ORDER BY created_at DESC LIMIT 1
            """, (inverter_id, f"{yesterday}%")).fetchone()
            return float(row["E_daily"]) if row and row["E_daily"] is not None else 0.0

    def get_yesterday_energy_by_project(self, project_id: int) -> float:
        """Tổng E_daily cuối ngày hôm qua của tất cả inverter trong project."""
        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with self._connect() as conn:
            # Lấy E_daily từ record cuối cùng của mỗi inverter trong ngày hôm qua
            rows = conn.execute("""
                SELECT E_daily FROM inverter_ac_realtime
                WHERE id IN (
                    SELECT MAX(id) FROM inverter_ac_realtime
                    WHERE project_id = ? AND created_at LIKE ?
                    GROUP BY inverter_id
                )
            """, (project_id, f"{yesterday}%")).fetchall()
            total = sum(float(r["E_daily"]) for r in rows if r["E_daily"] is not None)
            return round(total, 2)

    def get_yesterday_energy_per_inverter(self, project_id: int) -> dict:
        """Trả về {inverter_id: E_daily_yesterday} cho tất cả inverter trong project."""
        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT inverter_id, E_daily FROM inverter_ac_realtime
                WHERE id IN (
                    SELECT MAX(id) FROM inverter_ac_realtime
                    WHERE project_id = ? AND created_at LIKE ?
                    GROUP BY inverter_id
                )
            """, (project_id, f"{yesterday}%")).fetchall()
            return {r["inverter_id"]: float(r["E_daily"]) if r["E_daily"] is not None else 0.0 for r in rows}

