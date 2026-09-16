import time
import logging
import threading
from backend.db_manager import CacheDB, RealtimeDB
from backend.services.polling_service import PollingService
from backend.services.project_service import ProjectService
from backend.core import settings

logger = logging.getLogger(__name__)

class PollingWorker(threading.Thread):
    def __init__(self, project_svc: ProjectService, cache_db: CacheDB, realtime_db: RealtimeDB = None, logic_worker = None, interval: float = 10.0):
        super().__init__()
        self.cache_db = cache_db
        self.logic_worker = logic_worker
        self.service = PollingService(project_svc, cache_db, realtime_db)
        self.interval = interval
        self.daemon = True
        self._stop_event = threading.Event()
        
        # Đặt lại trạng thái bận của các cổng truyền thông khi khởi động dịch vụ Polling
        try:
            for i in range(1, 6):
                project_svc.metadata_db.set_setting(f"scanning_comm_{i}", "false")
        except Exception as e:
            logger.error(f"Failed to reset scanning status for comm ports: {e}")

    def stop(self):
        self._stop_event.set()

    def run(self):
        logger.info(f"Polling Worker started (Interval: {self.interval}s)")
        while not self._stop_event.is_set():
            t0 = time.time()
            try:
                logger.debug("--- Starting new Polling Cycle ---")
                # 1. Lấy cấu hình từ cache (hoặc database nếu hết hạn)
                polling_config = self.service.get_polling_config()
                
                for item in polling_config:
                    project = item["project"]
                    inverters = item["inverters"]
                    meters = item.get("meters", [])
                    
                    # 2. Quét dữ liệu Modbus theo Lô (Batch)
                    batch = self.service.poll_project_batch(project.id, inverters=inverters)
                    
                    # 3. Lưu Batch vào CacheDB
                    self.cache_db.commit_project_batch(batch)
                    
                    # 4. Quét Meter (vẫn xử lý riêng lẻ hoặc gộp sau)
                    self.service.poll_meters(project.id, meters=meters)
                    
                    # 5. Kích hoạt LogicWorker cho project này
                    if self.logic_worker:
                        self.logic_worker.trigger_project(project.id)
                    
            except Exception as e:
                logger.error(f"Error in Polling Worker cycle: {e}")
            
            elapsed = time.time() - t0
            sleep_time = max(0.1, self.interval - elapsed)
            time.sleep(sleep_time)
