import sqlite3
import logging
from typing import Optional, Dict, List, Any
from dataclasses import asdict, fields
from .base_db import BaseDB, to_dataclass

from backend.models.project import ProjectCreate, ProjectResponse, ProjectUpdate
from backend.models.inverter import InverterCreate, InverterResponse, InverterUpdate
from backend.models.battery import BatteryCreate, BatteryResponse, BatteryUpdate
from backend.models.meter import MeterCreate, MeterResponse, MeterUpdate
from backend.models.user import UserCreate, UserResponse
from backend.models.comm import CommConfig
from backend.models.server_account import (
    ServerAccountCreate,
    ServerAccountResponse,
    ServerAccountStored,
    ServerAccountUpdate,
)

logger = logging.getLogger(__name__)

class MetadataDB(BaseDB):
    """Quản lý cấu hình Project, Inverter, User và Communication."""
    
    def _connect(self):
        conn = super()._connect()
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    # =========================
    # SYSTEM SETTINGS
    # =========================
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
            row = c.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: Any):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET 
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """, (key, str(value)))
            conn.commit()

    def _create_tables(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            # Project table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_index INTEGER,
                elec_meter_no TEXT,
                elec_price_per_kwh REAL,
                name TEXT,
                location TEXT,
                lat REAL,
                lon REAL,
                capacity_kwp REAL,
                ac_capacity_kw REAL,
                inverter_count INTEGER,
                server_id INTEGER,
                server_request_id INTEGER,
                server_account_id INTEGER,
                sync_status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (server_account_id) REFERENCES server_accounts(id)
            );
            """)
            # Inverter table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS inverters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inverter_index INTEGER,
                serial_number TEXT UNIQUE,
                brand TEXT,
                model TEXT,
                firmware_version TEXT,
                phase_count INTEGER,
                mppt_count INTEGER,
                string_count INTEGER,
                strings_per_mppt INTEGER,
                capacity_kw REAL,
                rate_dc_kwp REAL,
                rate_ac_kw REAL,
                is_active BOOLEAN DEFAULT 1,
                replaced_by_id INTEGER,
                usage_start_at TEXT,
                usage_end_at TEXT,
                slave_id INTEGER,
                comm_id INTEGER,
                project_id INTEGER,
                server_id INTEGER,
                server_request_id INTEGER,
                sync_status TEXT DEFAULT 'pending',
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (replaced_by_id) REFERENCES inverters(id),
                FOREIGN KEY (comm_id) REFERENCES comm_config(id)
            );
            """)
            # User table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                email TEXT,
                fullname TEXT,
                phone TEXT,
                role TEXT DEFAULT 'user',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Server Accounts table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS server_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                username TEXT UNIQUE,
                password TEXT,
                token TEXT,
                refresh_token TEXT,
                expires_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Initialize default account if empty (migration support)
            cursor.execute("SELECT COUNT(*) as count FROM server_accounts")
            if cursor.fetchone()["count"] == 0:
                from backend.core.settings import API_USERNAME, API_PASSWORD
                cursor.execute(
                    "INSERT INTO server_accounts (id, name, username, password) VALUES (1, 'Default Account', ?, ?)",
                    (API_USERNAME, API_PASSWORD)
                )

            # Comm config
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS comm_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver TEXT,
                comm_type TEXT,
                host TEXT,
                port INTEGER,
                com_port TEXT,
                baudrate INTEGER,
                databits INTEGER,
                parity TEXT,
                stopbits INTEGER,
                timeout REAL,
                slave_id_start INTEGER,
                slave_id_end INTEGER,
                multi_master INTEGER DEFAULT 0,
                is_master INTEGER DEFAULT 1
            );
            """)

            # Seed default communication configurations (ID 1 to 6)
            for cid, dev, ctype, h, p, cp, br, db, pa, sb, to, st, en in [
                (1, "RS485_0", "RTU", "", 502, "/dev/ttyUSB0", 9600, 8, "N", 1, 1.0, 1, 30),
                (2, "RS485_1", "RTU", "", 502, "/dev/ttyUSB1", 9600, 8, "N", 1, 1.0, 1, 30),
                (3, "RS485_2", "RTU", "", 502, "/dev/ttyUSB2", 9600, 8, "N", 1, 1.0, 1, 30),
                (4, "RS485_3", "RTU", "", 502, "/dev/ttyUSB3", 9600, 8, "N", 1, 1.0, 1, 30),
                (5, "TCP 1", "TCP", "192.168.1.10", 502, "", 9600, 8, "N", 1, 1.0, 1, 30),
                (6, "TCP 2", "TCP", "192.168.1.11", 502, "", 9600, 8, "N", 1, 1.0, 1, 30),
            ]:
                cursor.execute("SELECT id FROM comm_config WHERE id = ?", (cid,))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO comm_config (id, driver, comm_type, host, port, com_port, baudrate, databits, parity, stopbits, timeout, slave_id_start, slave_id_end)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (cid, dev, ctype, h, p, cp, br, db, pa, sb, to, st, en))
            cursor.execute("UPDATE comm_config SET driver = 'TCP 1' WHERE id = 5 AND driver = 'TCP'")
            conn.commit()
            # Meters table
            cursor.execute('''CREATE TABLE IF NOT EXISTS meters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                brand TEXT NOT NULL,
                model TEXT NOT NULL,
                serial_number TEXT,
                slave_id INTEGER,
                comm_id INTEGER,
                ct_ratio REAL DEFAULT 1.0,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )''')

            # system_settings table
            cursor.execute('''CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')

            # control_audit_logs table
            cursor.execute('''CREATE TABLE IF NOT EXISTS control_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                inverter_id INTEGER,
                command_type TEXT NOT NULL,
                control_source TEXT NOT NULL,
                requested_value REAL NOT NULL,
                actual_value REAL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ctrl_audit_proj ON control_audit_logs(project_id, created_at)')

            # Batteries table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS batteries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                battery_index INTEGER,
                serial_number TEXT UNIQUE,
                brand TEXT,
                model TEXT,
                capacity_kwh REAL,
                capacity_ah REAL,
                num_parallel_connections INTEGER,
                cells_per_module INTEGER,
                modules_in_series INTEGER,
                is_active BOOLEAN DEFAULT 1,
                replaced_by_id INTEGER,
                usage_start_at TEXT,
                usage_end_at TEXT,
                project_id INTEGER,
                project_request_id INTEGER,
                server_id INTEGER,
                server_request_id INTEGER,
                sync_status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (replaced_by_id) REFERENCES batteries(id)
            );
            """)

            # Migration: Add EVN columns to projects if not exist
            self._ensure_column(conn, "projects", "evn_slave_id", "evn_slave_id INTEGER DEFAULT 1")
            self._ensure_column(conn, "projects", "evn_project_id", "evn_project_id INTEGER")
            self._ensure_column(conn, "projects", "sync_status", "sync_status TEXT DEFAULT 'pending'")
            self._ensure_column(conn, "inverters", "sync_status", "sync_status TEXT DEFAULT 'pending'")
            self._ensure_column(conn, "batteries", "sync_status", "sync_status TEXT DEFAULT 'pending'")
            self._ensure_column(conn, "inverters", "comm_id", "comm_id INTEGER")
            self._ensure_column(conn, "projects", "server_account_id", "server_account_id INTEGER")
            self._ensure_column(conn, "projects", "telemetry_mode", "telemetry_mode TEXT DEFAULT 'Realtime'")
            self._ensure_column(conn, "comm_config", "multi_master", "multi_master INTEGER DEFAULT 0")
            self._ensure_column(conn, "comm_config", "is_master", "is_master INTEGER DEFAULT 1")
            
            # Update existing projects to use account 1 if server_account_id is NULL
            cursor.execute("UPDATE projects SET server_account_id = 1 WHERE server_account_id IS NULL")
            conn.commit()

    # --- Project API ---
    def get_project(self, project_id: int) -> Optional[ProjectResponse]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            return to_dataclass(ProjectResponse, row)

    def get_projects(self) -> List[ProjectResponse]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
            return [to_dataclass(ProjectResponse, r) for r in rows]

    def upsert_project(self, data: ProjectCreate, project_id: Optional[int] = None) -> ProjectResponse:
        data_dict = asdict(data)
        with self._connect() as conn:
            cursor = conn.cursor()
            if project_id:
                # Update existing project (ignore None values)
                fields = []
                values = []
                for k, v in data_dict.items():
                    if v is not None:
                        fields.append(f"{k} = ?")
                        values.append(v)
                if not fields:
                    return self.get_project(project_id)
                values.append(project_id)
                cursor.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id=?", tuple(values))
                final_id = project_id
            else:
                # Insert new project
                row = conn.execute("SELECT MAX(project_index) as max_idx FROM projects").fetchone()
                next_idx = (row["max_idx"] or 0) + 1 if row else 1
                if data_dict.get("project_index") is not None:
                    next_idx = data_dict["project_index"]
                
                cursor.execute("""
                    INSERT INTO projects (
                        project_index, elec_meter_no, elec_price_per_kwh, name, location, lat, lon,
                        capacity_kwp, ac_capacity_kw, inverter_count, server_id, server_request_id,
                        server_account_id, telemetry_mode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (next_idx, data_dict.get("elec_meter_no"), data_dict.get("elec_price_per_kwh"),
                      data_dict.get("name"), data_dict.get("location"), data_dict.get("lat"), data_dict.get("lon"),
                      data_dict.get("capacity_kwp"), data_dict.get("ac_capacity_kw"), data_dict.get("inverter_count"),
                      data_dict.get("server_id"), data_dict.get("server_request_id"), data_dict.get("server_account_id"),
                      data_dict.get("telemetry_mode") or "Realtime"))
                final_id = cursor.lastrowid
                
            conn.commit()
            row = conn.execute("SELECT * FROM projects WHERE id=?", (final_id,)).fetchone()
            return to_dataclass(ProjectResponse, row)

    def post_project(self, data: ProjectCreate) -> int:
        data_dict = asdict(data)
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(project_index) as max_idx FROM projects").fetchone()
            next_idx = (row["max_idx"] or 0) + 1 if row else 1
            if data_dict.get("project_index") is not None:
                next_idx = data_dict["project_index"]
            cursor = conn.execute("""
                INSERT INTO projects (
                    project_index, elec_meter_no, elec_price_per_kwh, name, location, lat, lon,
                    capacity_kwp, ac_capacity_kw, inverter_count, server_id, server_request_id,
                    server_account_id, telemetry_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (next_idx, data_dict.get("elec_meter_no"), data_dict.get("elec_price_per_kwh"),
                  data_dict.get("name"), data_dict.get("location"), data_dict.get("lat"), data_dict.get("lon"),
                  data_dict.get("capacity_kwp"), data_dict.get("ac_capacity_kw"), data_dict.get("inverter_count"),
                  data_dict.get("server_id"), data_dict.get("server_request_id"), data_dict.get("server_account_id"),
                  data_dict.get("telemetry_mode") or "Realtime"))
            conn.commit()
            return cursor.lastrowid

    def patch_project(self, project_id: int, data: ProjectUpdate):
        data_dict = asdict(data)
        fields = [f"{k} = ?" for k, v in data_dict.items() if v is not None]
        values = [v for v in data_dict.values() if v is not None]
        if not fields: return
        values.append(project_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id=?", tuple(values))
            conn.commit()

    def update_project_sync(self, project_id: int, server_id: Optional[int] = None, server_request_id: Optional[int] = None, status: str = 'pending'):
        logger.info(f"[MetadataDB] Updating project {project_id} sync status to {status} (server_id={server_id})")
        with self._connect() as conn:
            conn.execute("""
                UPDATE projects 
                SET server_id = COALESCE(?, server_id), 
                    server_request_id = COALESCE(?, server_request_id),
                    sync_status = ? 
                WHERE id = ?
            """, (server_id, server_request_id, status, project_id))
            conn.commit()

    def get_project_sync_info(self, project_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT server_id, server_request_id, sync_status FROM projects WHERE id=?", (project_id,)).fetchone()
            return dict(row) if row else None

    def delete_project(self, project_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM batteries WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM meters WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM inverters WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            conn.commit()

    # --- Inverter API ---
    def get_inverter_by_id(self, inverter_id: int) -> Optional[InverterResponse]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM inverters WHERE id=?", (inverter_id,)).fetchone()
            return to_dataclass(InverterResponse, row)

    def get_inverter_by_serial(self, serial: str) -> Optional[InverterResponse]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM inverters WHERE serial_number=?", (serial,)).fetchone()
            return to_dataclass(InverterResponse, row)

    def get_inverters_by_project(self, project_id: int) -> List[InverterResponse]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM inverters WHERE project_id=? ORDER BY inverter_index ASC", (project_id,)).fetchall()
            return [to_dataclass(InverterResponse, r) for r in rows]

    def get_all_inverters(self) -> List[InverterResponse]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM inverters ORDER BY id ASC").fetchall()
            return [to_dataclass(InverterResponse, r) for r in rows]

    def upsert_inverter(self, data: InverterCreate) -> InverterResponse:
        data_dict = asdict(data)
        serial = data_dict.get("serial_number")
        with self._connect() as conn:
            cursor = conn.cursor()
            # Check if exists
            row = conn.execute("SELECT id FROM inverters WHERE serial_number=?", (serial,)).fetchone()
            if row:
                inv_id = row["id"]
                fields = []
                values = []
                for k, v in data_dict.items():
                    if k != "serial_number" and v is not None:
                        fields.append(f"{k} = ?")
                        values.append(v)
                if fields:
                    values.append(inv_id)
                    cursor.execute(f"UPDATE inverters SET {', '.join(fields)} WHERE id=?", tuple(values))
                final_id = inv_id
            else:
                # Insert
                keys = [k for k, v in data_dict.items() if v is not None]
                placeholders = ["?" for _ in keys]
                values = [data_dict[k] for k in keys]
                cursor.execute(f"INSERT INTO inverters ({', '.join(keys)}) VALUES ({', '.join(placeholders)})", tuple(values))
                final_id = cursor.lastrowid
            
            conn.commit()
            row = conn.execute("SELECT * FROM inverters WHERE id=?", (final_id,)).fetchone()
            return to_dataclass(InverterResponse, row)

    def patch_inverter(self, inverter_id: int, data: InverterUpdate):
        data_dict = asdict(data)
        logger.info(f"[MetadataDB] patch_inverter ID {inverter_id} - Incoming data: {data_dict}")
        if "is_active" in data_dict and data_dict["is_active"] is not None:
            val = data_dict["is_active"]
            if isinstance(val, str):
                data_dict["is_active"] = 0 if val.strip().lower() in ('0', 'false', 'off', 'disabled', 'inactive', 'ngưng hoạt động', 'ngung hoat dong', 'ngừng hoạt động', 'tắt', 'tat', 'stopped') else 1
            else:
                data_dict["is_active"] = 1 if val else 0
            logger.info(f"[MetadataDB] Evaluated is_active integer value for SQL: {data_dict['is_active']}")

        fields = [f"{k} = ?" for k, v in data_dict.items() if v is not None]
        values = [v for v in data_dict.values() if v is not None]
        if not fields:
            logger.warning(f"[MetadataDB] patch_inverter ID {inverter_id}: No fields to update!")
            return
        values.append(inverter_id)
        sql = f"UPDATE inverters SET {', '.join(fields)} WHERE id=?"
        logger.info(f"[MetadataDB] Executing SQL: {sql} | Values: {values}")
        with self._connect() as conn:
            cursor = conn.execute(sql, tuple(values))
            conn.commit()
            logger.info(f"[MetadataDB] SQL COMMIT successful for ID {inverter_id}. Rows affected: {cursor.rowcount}")

    def update_inverter_sync(self, inverter_id: int, server_id: Optional[int] = None, server_request_id: Optional[int] = None, status: str = 'pending'):
        with self._connect() as conn:
            conn.execute("""
                UPDATE inverters 
                SET server_id = COALESCE(?, server_id), 
                    server_request_id = COALESCE(?, server_request_id),
                    sync_status = ? 
                WHERE id = ?
            """, (server_id, server_request_id, status, inverter_id))
            conn.commit()

    def delete_inverter(self, inverter_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM inverters WHERE id=?", (inverter_id,))
            conn.commit()

    # --- Battery API ---
    def get_battery_by_id(self, battery_id: int) -> Optional[BatteryResponse]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM batteries WHERE id=?", (battery_id,)).fetchone()
            return to_dataclass(BatteryResponse, row)

    def get_battery_by_serial(self, serial: str) -> Optional[BatteryResponse]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM batteries WHERE serial_number=?", (serial,)).fetchone()
            return to_dataclass(BatteryResponse, row)

    def get_batteries_by_project(self, project_id: int) -> List[BatteryResponse]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM batteries WHERE project_id=? ORDER BY battery_index ASC, id ASC", (project_id,)).fetchall()
            return [to_dataclass(BatteryResponse, r) for r in rows]

    def get_all_batteries(self) -> List[BatteryResponse]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM batteries ORDER BY id ASC").fetchall()
            return [to_dataclass(BatteryResponse, r) for r in rows]

    def upsert_battery(self, data: BatteryCreate) -> BatteryResponse:
        data_dict = asdict(data)
        serial = data_dict.get("serial_number")
        with self._connect() as conn:
            cursor = conn.cursor()
            row = conn.execute("SELECT id FROM batteries WHERE serial_number=?", (serial,)).fetchone()
            if row:
                batt_id = row["id"]
                fields = []
                values = []
                for k, v in data_dict.items():
                    if k != "serial_number" and v is not None:
                        fields.append(f"{k} = ?")
                        values.append(v)
                if fields:
                    fields.append("updated_at = CURRENT_TIMESTAMP")
                    values.append(batt_id)
                    cursor.execute(f"UPDATE batteries SET {', '.join(fields)} WHERE id=?", tuple(values))
                final_id = batt_id
            else:
                keys = [k for k, v in data_dict.items() if v is not None]
                placeholders = ["?" for _ in keys]
                values = [data_dict[k] for k in keys]
                cursor.execute(f"INSERT INTO batteries ({', '.join(keys)}) VALUES ({', '.join(placeholders)})", tuple(values))
                final_id = cursor.lastrowid
            
            conn.commit()
            row = conn.execute("SELECT * FROM batteries WHERE id=?", (final_id,)).fetchone()
            return to_dataclass(BatteryResponse, row)

    def post_battery(self, data: BatteryCreate) -> int:
        res = self.upsert_battery(data)
        return res.id

    def patch_battery(self, battery_id: int, data: BatteryUpdate):
        data_dict = asdict(data)
        if "is_active" in data_dict and data_dict["is_active"] is not None:
            val = data_dict["is_active"]
            if isinstance(val, str):
                data_dict["is_active"] = 0 if val.strip().lower() in ('0', 'false', 'off', 'disabled', 'inactive', 'tắt', 'stopped') else 1
            else:
                data_dict["is_active"] = 1 if val else 0

        fields = [f"{k} = ?" for k, v in data_dict.items() if v is not None]
        values = [v for v in data_dict.values() if v is not None]
        if not fields:
            return
        fields.append("updated_at = CURRENT_TIMESTAMP")
        values.append(battery_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE batteries SET {', '.join(fields)} WHERE id=?", tuple(values))
            conn.commit()

    def update_battery_sync(self, battery_id: int, server_id: Optional[int] = None, server_request_id: Optional[int] = None, status: str = 'pending'):
        with self._connect() as conn:
            conn.execute("""
                UPDATE batteries 
                SET server_id = COALESCE(?, server_id), 
                    server_request_id = COALESCE(?, server_request_id),
                    sync_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (server_id, server_request_id, status, battery_id))
            conn.commit()

    def delete_battery(self, battery_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM batteries WHERE id=?", (battery_id,))
            conn.commit()

    # --- Comm/Auth API (Rút gọn) ---
    def get_comm_config(self) -> List[CommConfig]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM comm_config").fetchall()
            return [to_dataclass(CommConfig, r) for r in rows]

    def get_comm(self) -> List[CommConfig]:
        """Tương đương get_comm_config."""
        return self.get_comm_config()

    def get_comm_id(self, config_id: int) -> Optional[CommConfig]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM comm_config WHERE id=?", (config_id,)).fetchone()
            return to_dataclass(CommConfig, row)

    def post_comm(self, data: CommConfig) -> int:
        data_dict = asdict(data)
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO comm_config (
                    driver, comm_type, host, port, com_port, baudrate, databits, parity, stopbits, timeout, slave_id_start, slave_id_end, multi_master, is_master
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data_dict.get("driver"), data_dict.get("comm_type"), data_dict.get("host"), data_dict.get("port"),
                  data_dict.get("com_port"), data_dict.get("baudrate"), data_dict.get("databits"), data_dict.get("parity"),
                  data_dict.get("stopbits"), data_dict.get("timeout"), data_dict.get("slave_id_start"), data_dict.get("slave_id_end"),
                  1 if data_dict.get("multi_master") else 0,
                  0 if data_dict.get("is_master") is False else 1))
            conn.commit()
            return cursor.lastrowid

    def patch_comm(self, config_id: int, updates: dict):
        with self._connect() as conn:
            fields = []
            values = []
            for k, v in updates.items():
                fields.append(f"{k} = ?")
                values.append(v)
            if not fields: return
            values.append(config_id)
            conn.execute(f"UPDATE comm_config SET {', '.join(fields)} WHERE id=?", tuple(values))
            conn.commit()

    def delete_comm(self, config_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM comm_config WHERE id=?", (config_id,))
            conn.commit()

    def reset_comm(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM comm_config")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='comm_config'")
            conn.commit()

    # --- User API ---
    def get_user_by_name(self, username: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    def create_user(self, data: UserCreate) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, hashed_password, email, fullname, phone, role) VALUES (?, ?, ?, ?, ?, ?)",
                (data.username, data.password, data.email, data.fullname, data.phone, data.role)
            )
            conn.commit()
            return cursor.lastrowid

    # --- Server Account API ---
    def get_server_account(self, account_id: int) -> Optional[ServerAccountResponse]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM server_accounts WHERE id=?", (account_id,)).fetchone()
            return to_dataclass(ServerAccountResponse, row)

    def get_server_account_for_auth(self, account_id: int) -> Optional[ServerAccountStored]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM server_accounts WHERE id=?", (account_id,)).fetchone()
            return to_dataclass(ServerAccountStored, row)

    def get_server_accounts(self) -> List[ServerAccountResponse]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM server_accounts ORDER BY id ASC").fetchall()
            return [to_dataclass(ServerAccountResponse, r) for r in rows]

    def upsert_server_account(
        self,
        data: ServerAccountCreate | ServerAccountUpdate,
        account_id: Optional[int] = None,
    ) -> ServerAccountResponse:
        data_dict = asdict(data)
        with self._connect() as conn:
            cursor = conn.cursor()
            if account_id:
                # Update existing account
                fields = []
                values = []
                for k, v in data_dict.items():
                    if v is not None:
                        fields.append(f"{k} = ?")
                        values.append(v)
                if not fields:
                    return self.get_server_account(account_id)
                values.append(account_id)
                cursor.execute(f"UPDATE server_accounts SET {', '.join(fields)} WHERE id=?", tuple(values))
                final_id = account_id
            else:
                # Insert new account
                cursor.execute("""
                    INSERT INTO server_accounts (name, username, password) VALUES (?, ?, ?)
                """, (data_dict.get("name"), data_dict.get("username"), data_dict.get("password")))
                final_id = cursor.lastrowid
                
            conn.commit()
            row = conn.execute("SELECT * FROM server_accounts WHERE id=?", (final_id,)).fetchone()
            return to_dataclass(ServerAccountResponse, row)

    def patch_server_account(self, account_id: int, data: ServerAccountUpdate):
        data_dict = asdict(data)
        fields = [f"{k} = ?" for k, v in data_dict.items() if v is not None]
        values = [v for v in data_dict.values() if v is not None]
        if not fields: return
        values.append(account_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE server_accounts SET {', '.join(fields)} WHERE id=?", tuple(values))
            conn.commit()

    def delete_server_account(self, account_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM server_accounts WHERE id=?", (account_id,))
            conn.commit()

    # --- Meter API ---
    def get_meter(self, meter_id: int) -> Optional[MeterResponse]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM meters WHERE id=?", (meter_id,)).fetchone()
            return to_dataclass(MeterResponse, row)

    def get_meters_by_project(self, project_id: int) -> List[MeterResponse]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM meters WHERE project_id=? ORDER BY id ASC", (project_id,)).fetchall()
            return [to_dataclass(MeterResponse, r) for r in rows]

    def upsert_meter(self, data: MeterCreate) -> MeterResponse:
        data_dict = asdict(data)
        serial = data_dict.get("serial_number")
        with self._connect() as conn:
            cursor = conn.cursor()
            row = conn.execute("SELECT id FROM meters WHERE serial_number=?", (serial,)).fetchone()
            if row:
                meter_id = row["id"]
                fields = []
                values = []
                for k, v in data_dict.items():
                    if k != "serial_number" and v is not None:
                        fields.append(f"{k} = ?")
                        values.append(v)
                if fields:
                    values.append(meter_id)
                    cursor.execute(f"UPDATE meters SET {', '.join(fields)} WHERE id=?", tuple(values))
                final_id = meter_id
            else:
                keys = [k for k, v in data_dict.items() if v is not None]
                placeholders = ["?" for _ in keys]
                values = [data_dict[k] for k in keys]
                cursor.execute(f"INSERT INTO meters ({', '.join(keys)}) VALUES ({', '.join(placeholders)})", tuple(values))
                final_id = cursor.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM meters WHERE id=?", (final_id,)).fetchone()
            return to_dataclass(MeterResponse, row)

    def post_meter(self, data: MeterCreate) -> int:
        data_dict = asdict(data)
        with self._connect() as conn:
            keys = [k for k, v in data_dict.items() if v is not None]
            placeholders = ["?" for _ in keys]
            values = [data_dict[k] for k in keys]
            cursor = conn.execute(f"INSERT INTO meters ({', '.join(keys)}) VALUES ({', '.join(placeholders)})", tuple(values))
            conn.commit()
            return cursor.lastrowid

    def patch_meter(self, meter_id: int, data: MeterUpdate):
        data_dict = asdict(data)
        fields = [f"{k} = ?" for k, v in data_dict.items() if v is not None]
        values = [v for v in data_dict.values() if v is not None]
        if not fields: return
        values.append(meter_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE meters SET {', '.join(fields)} WHERE id=?", tuple(values))
            conn.commit()

    def delete_meter(self, meter_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM meters WHERE id=?", (meter_id,))
            conn.commit()

    # --- EVN Project Mapping ---
    def get_evn_project_map(self) -> Dict[int, ProjectResponse]:
        """Trả về {evn_slave_id: ProjectResponse} cho tất cả project có evn_slave_id > 0."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects WHERE evn_slave_id > 0 ORDER BY evn_slave_id ASC").fetchall()
            return {to_dataclass(ProjectResponse, r).evn_slave_id: to_dataclass(ProjectResponse, r) for r in rows}

    # --- Zero Export Config ---
    def get_zero_export_config(self, project_id: int) -> dict:
        """Đọc cấu hình Zero Export của một project từ system_settings.
        
        Keys được lưu dạng: ze_{project_id}_{param}
        Trả về dict với tất cả các tham số, dùng giá trị mặc định nếu chưa cấu hình.
        """
        from backend.core import settings as app_settings
        pid = project_id
        return {
            "project_id":           pid,
            "enabled":              self.get_setting(f"ze_{pid}_enabled", "false").lower() == "true",
            "meter_id":             int(self.get_setting(f"ze_{pid}_meter_id", 0)) or None,
            "meter_direction":      self.get_setting(f"ze_{pid}_meter_direction", "GRID_SIDE"),
            "export_limit_w":       float(self.get_setting(f"ze_{pid}_export_limit_w", "0.0")),
            "deadband_w":           float(self.get_setting(f"ze_{pid}_deadband_w", str(app_settings.ZERO_EXPORT_DEFAULT_DEADBAND_W))),
            "gain":                 float(self.get_setting(f"ze_{pid}_gain", str(app_settings.ZERO_EXPORT_DEFAULT_GAIN))),
            "ramp_kw_per_step":     float(self.get_setting(f"ze_{pid}_ramp_kw_per_step", str(app_settings.ZERO_EXPORT_DEFAULT_RAMP_KW))),
            "meter_fail_threshold": int(self.get_setting(f"ze_{pid}_meter_fail_threshold", str(app_settings.ZERO_EXPORT_METER_FAIL_THRESHOLD))),
        }

    def set_zero_export_config(self, project_id: int, config: dict):
        """Lưu cấu hình Zero Export của một project vào system_settings.
        
        Chỉ lưu các key có trong config dict (partial update được hỗ trợ).
        """
        pid = project_id
        key_map = {
            "enabled":              f"ze_{pid}_enabled",
            "meter_id":             f"ze_{pid}_meter_id",
            "meter_direction":      f"ze_{pid}_meter_direction",
            "export_limit_w":       f"ze_{pid}_export_limit_w",
            "deadband_w":           f"ze_{pid}_deadband_w",
            "gain":                 f"ze_{pid}_gain",
            "ramp_kw_per_step":     f"ze_{pid}_ramp_kw_per_step",
            "meter_fail_threshold": f"ze_{pid}_meter_fail_threshold",
        }
        for field, setting_key in key_map.items():
            if field in config and config[field] is not None:
                self.set_setting(setting_key, str(config[field]))
        logger.info(f"[MetadataDB] Saved Zero Export config for project {project_id}: {config}")

    def write_control_audit_log(
        self,
        project_id: int,
        inverter_id: Optional[int],
        command_type: str,
        control_source: str,
        requested_value: float,
        actual_value: Optional[float],
        status: str,
        error_message: Optional[str] = None,
    ):
        """Ghi nhận lịch sử lệnh điều khiển (Audit Log) an toàn."""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO control_audit_logs (
                        project_id, inverter_id, command_type, control_source,
                        requested_value, actual_value, status, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (project_id, inverter_id, command_type, control_source,
                      requested_value, actual_value, status, error_message))
                conn.commit()
        except Exception as e:
            logger.error(f"[MetadataDB] Failed to write control audit log: {e}", exc_info=True)

