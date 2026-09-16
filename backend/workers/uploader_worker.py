import time
import logging
import threading
from backend.db_manager import CacheDB, RealtimeDB
from backend.services.project_service import ProjectService
from backend.services.uploader_service import UploaderService
from backend.services.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)

# Số bản ghi tối đa giữ trong outbox.
# Nếu server liên tục trả 4xx (record bị giữ lại), outbox sẽ bị giới hạn tại đây.
# Các record cũ nhất sẽ bị xóa trước để nhường chỗ cho dữ liệu mới hơn.
MAX_OUTBOX_ROWS = 500

class UploaderWorker(threading.Thread):
    def __init__(self, cache_db: CacheDB, project_svc: ProjectService, realtime_db: RealtimeDB, upload_interval: float = 300.0):
        super().__init__()
        self.cache_db = cache_db
        self.project_svc = project_svc
        self.realtime_db = realtime_db
        # Ta cần MetadataDB để UploaderService tra cứu Server Account
        self.uploader = UploaderService(realtime_db, project_svc.metadata_db)
        self.telemetry = TelemetryService(realtime_db)
        self.upload_interval = upload_interval
        self.daemon = True
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        logger.info(f"Uploader Worker started (Interval: {self.upload_interval}s)")
        
        # Đợi Persistence Worker chạy xong lượt Snapshot đầu tiên
        time.sleep(15)
        
        while not self._stop_event.is_set():
            try:
                # 1. Gửi lại outbox tồn đọng từ chu kỳ trước (nếu có)
                logger.info("Uploader Worker: Checking previous outbox for retry upload...")
                self.uploader.upload()

                # 2. Xây gói dữ liệu mới của chu kỳ này
                projects = self.project_svc.get_projects()
                new_payloads = 0
                for proj in projects:
                    if not proj.server_id: continue
                    invs = self.project_svc.get_inverters_by_project(proj.id)
                    payload_list = self.telemetry.build_payload_from_cache(proj.id, proj.server_id, invs, self.cache_db)
                    
                    if payload_list:
                        # 3. Quăng vào outbox trước để lỡ cúp điện thì không mất
                        self.realtime_db.post_to_outbox(proj.id, proj.server_id, payload_list[0], data_type="Project")
                        new_payloads += 1
                
                if new_payloads > 0:
                    logger.info(f"Uploader Worker: Generated {new_payloads} new payloads. Initiating upload...")
                    # 4. Gửi các gói mới vừa được đưa vào outbox
                    self.uploader.upload()

                # 5. Giới hạn kích thước outbox để tránh tích lũy vô hạn
                #    (xảy ra khi server liên tục trả 4xx và record bị giữ lại)
                self.realtime_db.trim_outbox(MAX_OUTBOX_ROWS)

            except Exception as e:
                logger.error(f"Error in Uploader Worker cycle: {e}")
            
            time.sleep(self.upload_interval)
