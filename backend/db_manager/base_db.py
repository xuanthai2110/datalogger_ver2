import threading
import sqlite3
import logging
from typing import Any, List, Optional
from dataclasses import fields

logger = logging.getLogger(__name__)

def to_dataclass(cls, row):
    if row is None: return None
    d = dict(row)
    # Filter only fields present in dataclass
    cls_fields = {f.name for f in fields(cls)}
    filtered = {k: v for k, v in d.items() if k in cls_fields}
    if 'is_active' in filtered and filtered['is_active'] is not None:
        val = filtered['is_active']
        if isinstance(val, str):
            filtered['is_active'] = val.strip().lower() not in ('0', 'false', 'off', 'disabled', 'inactive', 'ngưng hoạt động', 'ngung hoat dong', 'ngừng hoạt động', 'tắt', 'tat', 'stopped')
        else:
            filtered['is_active'] = bool(val)
    return cls(**filtered)

class BaseDB:
    """Lớp cơ sở cho các kết nối SQLite, cung cấp logic kết nối và tối ưu hóa."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_journal_mode()
        self._create_tables()

    def _init_journal_mode(self):
        """Khởi tạo WAL mode một lần duy nhất khi tạo instance đối tượng DB."""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA busy_timeout = 30000;")
        except Exception as e:
            logger.warning(f"[BaseDB] Could not set WAL mode on init for {self.db_path}: {e}")

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA busy_timeout = 30000;")
        except Exception:
            pass
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self):
        """Sẽ được ghi đè bởi lớp con."""
        pass

    def _ensure_column(self, conn, table_name: str, column_name: str, column_sql: str):
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")
