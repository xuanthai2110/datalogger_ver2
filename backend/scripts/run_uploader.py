import os
import sys
import time
import logging
from pathlib import Path

# Thêm thư mục gốc vào sys.path để import được các module trong backend/
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from backend.db_manager.metadata import MetadataDB
from backend.db_manager.realtime import RealtimeDB
from backend.services.uploader_service import UploaderService
from backend.core import settings

from backend.core.logger import setup_logging
setup_logging()
logger = logging.getLogger("Uploader")


def main():
    logger.info("Starting Telemetry Uploader Script...")
    
    # 1. Initialize DBs
    meta_db = MetadataDB(settings.METADATA_DB)
    realtime_db = RealtimeDB(settings.REALTIME_DB)
    
    # 2. Initialize UploaderService
    uploader = UploaderService(realtime_db, meta_db)
    
    logger.info("Uploader service ready. Monitoring outbox table...")
    
    while True:
        try:
            # Kiểm kê và gửi dữ liệu từ outbox
            uploader.upload()
        except Exception as e:
            logger.error(f"Uploader loop error: {e}")
        
        # Nghỉ 10 giây trước khi kiểm tra lại
        time.sleep(10)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Uploader stopped by user.")
    except Exception as e:
        logger.error(f"Uploader error: {e}", exc_info=True)
