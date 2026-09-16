import sys
import os
import logging
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db_manager import MetadataDB, CacheDB, RealtimeDB
from backend.services.modbus_server_service import ModbusServerService
from backend.services.project_service import ProjectService
from backend.workers.evn_worker import EVNWorker
from backend.core import settings

from backend.core.logger import setup_logging
setup_logging()
logger = logging.getLogger("EVNLauncher")


def main():
    try:
        logger.info("Starting Dedicated EVN Service...")
        
        # 1. DB Layer
        meta_db = MetadataDB(settings.METADATA_DB)
        cache_db = CacheDB(settings.CACHE_DB)
        realtime_db = RealtimeDB(settings.REALTIME_DB)
        
        # 2. Service Layer
        project_svc = ProjectService(metadata_db=meta_db, realtime_db=realtime_db)
        
        # 3. Kiểm tra EVN có được bật không
        evn_enabled = meta_db.get_setting("evn_enabled", str(settings.EVN_ENABLED)).lower() == "true"
        if not evn_enabled:
            logger.info("EVN Integration is disabled in settings. Exiting.")
            return

        # Cấu hình IP/Port
        host = meta_db.get_setting("evn_modbus_host", settings.EVN_MODBUS_HOST)
        # Trong container Docker, luôn phải bind vào 0.0.0.0
        bind_host = "0.0.0.0" if os.path.exists("/.dockerenv") else host
        port = int(meta_db.get_setting("evn_modbus_port", settings.EVN_MODBUS_PORT))
        
        # 4. Lấy danh sách slave_id và IP được phép
        evn_map = meta_db.get_evn_project_map()
        slave_ids = list(evn_map.keys())

        if not slave_ids:
            logger.warning("No EVN project configured (evn_slave_id). Exiting.")
            return

        allowed_ips_str = meta_db.get_setting("evn_allowed_ips", settings.EVN_ALLOWED_IPS)
        allowed_ips_list = [ip.strip() for ip in allowed_ips_str.split(",") if ip.strip()]

        # 5. Khởi chạy Modbus Server
        modbus_server = ModbusServerService()
        logger.info(f"Starting Modbus Server at {bind_host}:{port} (External access via {host}) | Allowed IPs: {allowed_ips_list or 'ALL'}")
        modbus_server.start(bind_host, port, slave_ids, allowed_ips=allowed_ips_list)

        # 6. Khởi chạy EVNWorker
        # Lưu ý: control_service=None vì điều khiển được thực hiện qua DB (evn_control_commands)
        # Container Polling sẽ đọc lệnh từ DB và thực hiện qua EVNCommandWorker
        evn_worker = EVNWorker(
            modbus_server=modbus_server,
            cache_db=cache_db,
            realtime_db=realtime_db,
            metadata_db=meta_db,
            project_svc=project_svc,
            control_service=None,
        )
        evn_worker.start()
        
        logger.info("EVN Service operational. Press Ctrl+C to exit.")
        while True:
            time.sleep(10)

    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    except Exception as e:
        logger.error(f"EVN Service error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
