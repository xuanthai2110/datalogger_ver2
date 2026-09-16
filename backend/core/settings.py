import os
from pathlib import Path
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# Load environment variables from .env file
# This assumes .env is at the root of the project (e:\datalogger_project_2102)
# We find it by going up one level from 'backend'
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() # Fallback to default search

# ===========================================================
# SERVER BINDING
# ===========================================================
RUNNING_IN_DOCKER = Path("/.dockerenv").exists()
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_BIND_HOST = os.getenv(
    "WEB_BIND_HOST",
    "0.0.0.0" if RUNNING_IN_DOCKER else WEB_HOST,
)
WEB_PUBLIC_HOST = os.getenv("WEB_PUBLIC_HOST", WEB_HOST)
WEB_PORT = int(os.getenv("WEB_PORT", "5000"))

# ===========================================================
# PATHS
# ===========================================================
DATABASE_DIR = BASE_DIR / "db_manager" / "data"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)


METADATA_DB    = str(DATABASE_DIR / "metadata.db")
REALTIME_DB    = str(DATABASE_DIR / "realtime.db")

# CACHE_DB: Dữ liệu thực tế 10s lưu trên RAM để bảo vệ thẻ SD
if os.path.exists("/dev/shm"):
    CACHE_DB = "/dev/shm/hirubic_cache.db"
else:
    CACHE_DB = str(DATABASE_DIR / "cache.db")

# ===========================================================
# API
# ===========================================================
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.hivision.vn").rstrip("/")
DEV_MODE     = os.getenv("DEV_MODE", "True").lower() in ("true", "1", "yes")
API_USERNAME = os.getenv("API_USERNAME", "")
API_PASSWORD = os.getenv("API_PASSWORD", "")

# ===========================================================
# POLLING   
# ===========================================================
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
SNAPSHOT_INTERVAL = int(os.getenv("SNAPSHOT_INTERVAL", "300"))
CONFIG_REFRESH_INTERVAL = int(os.getenv("CONFIG_REFRESH_INTERVAL", "300"))
DATA_RETENTION_DAYS = 30 # Lưu trữ tối đa 60 ngày

# ===========================================================
# COMMUNICATION (CommConfig defaults)
# ===========================================================
DRIVER = os.getenv("DRIVER", "Huawei")
COMM_TYPE = os.getenv("COMM_TYPE", "TCP")
MODBUS_TCP_HOST = os.getenv("MODBUS_TCP_HOST", "192.168.1.8")
MODBUS_TCP_PORT = int(os.getenv("MODBUS_TCP_PORT", "502"))
MODBUS_PORT     = os.getenv("MODBUS_PORT", "/dev/ttyUSB0")
MODBUS_BAUDRATE = int(os.getenv("MODBUS_BAUDRATE", "9600"))
DATABITS        = int(os.getenv("DATABITS", "8"))
PARITY          = os.getenv("PARITY", "N")
STOPBITS        = int(os.getenv("STOPBITS", "1"))
TIMEOUT         = float(os.getenv("TIMEOUT", "1.0"))
SLAVE_ID_START  = int(os.getenv("SLAVE_ID_START", "1"))
SLAVE_ID_END    = int(os.getenv("SLAVE_ID_END", "30"))
RETRIES         = int(os.getenv("RETRIES", "1"))
MODBUS_MULTI_MASTER = os.getenv("MODBUS_MULTI_MASTER", "False").lower() in ("true", "1", "yes")

# PROJECT scope MAXP: per-inverter loop (no SmartLogger)
PROJECT_MAXP_CONTROL_INTERVAL_SEC = int(os.getenv("PROJECT_MAXP_CONTROL_INTERVAL_SEC", "10"))
PROJECT_MAXP_POWER_WEIGHT_EPS_W = float(os.getenv("PROJECT_MAXP_POWER_WEIGHT_EPS_W", "50.0"))

# ===========================================================
# EVN MODBUS TCP SERVER
# ===========================================================
EVN_ENABLED = os.getenv("EVN_ENABLED", "False").lower() in ("true", "1", "yes")
EVN_MODBUS_HOST = os.getenv("EVN_MODBUS_HOST", "0.0.0.0")
EVN_MODBUS_PORT = int(os.getenv("EVN_MODBUS_PORT", "502"))
EVN_ALLOWED_IPS = os.getenv("EVN_ALLOWED_IPS", "") # Danh sách IP cách nhau bằng dấu phẩy
EVN_TELEMETRY_INTERVAL = int(os.getenv("EVN_TELEMETRY_INTERVAL", "300"))  # 5 phút

# ===========================================================
# MQTT (Control Scheduling & Telemetry)
# ===========================================================
MQTT_BROKER   = os.getenv("MQTT_BROKER", "14.224.236.53")
MQTT_PORT     = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "admin")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "@Dm!n")

# ===========================================================
# PROJECT INFO
# ===========================================================
PROJECT_INFO = {
    "elec_meter_no": "PC07FF0169923",
    "elec_price_per_kwh": 1783,
    "name": "NBC-Nha Be",
    "location": "Quảng Ngãi",
    "lat": 14.821533,
    "lon": 108.945834,
    "capacity_kwp": 1000,
    "ac_capacity_kw": 880,
    "inverter_count": 8,
}

# ===========================================================
# LOCAL AUTH (WEB UI)
# ===========================================================
SECRET_KEY = os.getenv("SECRET_KEY", "hirubic_local_secret_key_change_me")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_MINUTES = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", "10080")) # 7 days default

# ===========================================================
# ZERO EXPORT
# ===========================================================
ZERO_EXPORT_INTERVAL_SEC        = int(os.getenv("ZERO_EXPORT_INTERVAL_SEC", "10"))
ZERO_EXPORT_DEFAULT_DEADBAND_W  = float(os.getenv("ZERO_EXPORT_DEFAULT_DEADBAND_W", "200"))
ZERO_EXPORT_DEFAULT_GAIN        = float(os.getenv("ZERO_EXPORT_DEFAULT_GAIN", "1.0"))
ZERO_EXPORT_DEFAULT_RAMP_KW     = float(os.getenv("ZERO_EXPORT_DEFAULT_RAMP_KW", "50.0"))
ZERO_EXPORT_METER_FAIL_THRESHOLD = int(os.getenv("ZERO_EXPORT_METER_FAIL_THRESHOLD", "10"))
# Số lần meter mất kết nối liên tiếp (×10s = 100s) trước khi set inverter = 0 kW và báo METER_FAULT
