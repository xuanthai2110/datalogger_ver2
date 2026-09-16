"""
backend/workers/zero_export_worker.py

Worker chạy vòng lặp Zero Export — gọi ZeroExportService.run_cycle() mỗi INTERVAL giây.

Chạy song song với PollingWorker và LogicWorker.
Tự động xử lý:
    - Bật/tắt ZE theo cấu hình per-project
    - Nhường quyền cho EVN và Server schedule
    - Khôi phục tự động khi không còn lock/schedule
"""
import time
import logging
import threading

from backend.services.zero_export_service import ZeroExportService
from backend.services.polling_service import PollingService
from backend.core import settings as app_settings

logger = logging.getLogger(__name__)


class ZeroExportWorker(threading.Thread):
    """Worker thread chạy Zero Export điều khiển độc lập với polling."""

    def __init__(
        self,
        ze_service: ZeroExportService,
        polling_service: PollingService,
        interval: float = None,
    ):
        super().__init__()
        self.ze_service = ze_service
        self.polling_service = polling_service
        self.interval = interval if interval is not None else float(app_settings.ZERO_EXPORT_INTERVAL_SEC)
        self.daemon = True
        self._stop_event = threading.Event()
        self.name = "ZeroExportWorker"

    def stop(self):
        self._stop_event.set()

    def run(self):
        logger.info(
            "[ZeroExportWorker] Started (interval=%.1fs)", self.interval
        )
        while not self._stop_event.is_set():
            t0 = time.time()
            try:
                self._run_all_projects()
            except Exception as e:
                logger.error("[ZeroExportWorker] Unexpected error in main loop: %s", e, exc_info=True)

            elapsed = time.time() - t0
            sleep_time = max(0.1, self.interval - elapsed)
            self._stop_event.wait(timeout=sleep_time)

    def _run_all_projects(self):
        """Chạy một chu kỳ Zero Export cho tất cả projects đang active."""
        try:
            polling_config = self.polling_service.get_polling_config()
        except Exception as e:
            logger.error("[ZeroExportWorker] Failed to get polling config: %s", e)
            return

        for item in polling_config:
            project = item.get("project")
            if not project:
                continue

            project_id = project.id
            try:
                self.ze_service.run_cycle(project_id)
            except Exception as e:
                logger.error(
                    "[ZeroExportWorker] Error running cycle for project %s: %s",
                    project_id, e, exc_info=True,
                )
