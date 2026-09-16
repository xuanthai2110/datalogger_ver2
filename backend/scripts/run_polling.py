import sys
import os
import logging
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db_manager import MetadataDB, CacheDB, RealtimeDB
from backend.workers.polling_worker import PollingWorker
from backend.workers.logic_worker import LogicWorker
from backend.workers.persistence_worker import PersistenceWorker
from backend.workers.build_tele_worker import BuildTeleWorker
from backend.workers.schedule_worker import ScheduleWorker
from backend.workers.evn_command_worker import EVNCommandWorker
from backend.workers.zero_export_worker import ZeroExportWorker
from backend.services.fault_service import FaultService
from backend.services.project_service import ProjectService
from backend.services.schedule_service import ScheduleService
from backend.services.control_service import ControlService
from backend.services.zero_export_service import ZeroExportService
from backend.communication.mqtt_subscriber import MqttSubscriber
from backend.core import settings

from backend.core.logger import setup_logging
setup_logging()
logger = logging.getLogger("Launcher")


def main():
    try:
        logger.info(f"System Path prioritized: {sys.path[0]}")
        logger.info("Starting Modular Telemetry Datalogger (Polling & Logic)...")
        
        # 1. DB Layer
        meta_db = MetadataDB(settings.METADATA_DB)
        cache_db = CacheDB(settings.CACHE_DB)
        realtime_db = RealtimeDB(settings.REALTIME_DB)
        
        # 2. Service Layer
        project_svc = ProjectService(metadata_db=meta_db, realtime_db=realtime_db)
        fault_service = FaultService(realtime_db, meta_db)
        schedule_svc = ScheduleService(realtime_db, meta_db)
        
        # 3. Worker Layer
        build_tele_worker = BuildTeleWorker(cache_db, project_svc, realtime_db, settings.SNAPSHOT_INTERVAL)
        
        # LogicWorker cần được khởi tạo trước PollingWorker để PollingWorker có thể gửi tín hiệu trigger
        logic_worker = LogicWorker(cache_db, project_svc, realtime_db, fault_service, build_tele_worker)
        
        poll_worker = PollingWorker(
            project_svc=project_svc, 
            cache_db=cache_db, 
            realtime_db=realtime_db, 
            logic_worker=logic_worker, 
            interval=settings.POLL_INTERVAL
        )
        
        persist_worker = PersistenceWorker(
            cache_db, realtime_db,
            logic_worker.energy_service,
            settings.SNAPSHOT_INTERVAL,
            string_monitor=poll_worker.service.string_monitor
        )
        
        # 4. Control Service
        control_svc = ControlService(polling_service=poll_worker.service)

        # 5. EVN Command Worker — đọc lệnh từ DB do container EVN ghi vào
        evn_command_worker = EVNCommandWorker(
            realtime_db=realtime_db,
            control_service=control_svc,
        )

        # 6. Zero Export
        ze_service = ZeroExportService(
            cache_db=cache_db,
            metadata_db=meta_db,
            control_service=control_svc,
            polling_service=poll_worker.service,
            schedule_service=schedule_svc,
        )
        ze_worker = ZeroExportWorker(
            ze_service=ze_service,
            polling_service=poll_worker.service,
            interval=settings.ZERO_EXPORT_INTERVAL_SEC,
        )
        # Expose ze_service vào app.py để API endpoint có thể dùng (trong cùng process)
        try:
            import backend.app as _app_module
            _app_module.ze_service_instance = ze_service
            logger.info("[run_polling] ZeroExportService injected into app module.")
        except Exception as _e:
            logger.warning("[run_polling] Could not inject ze_service into app module: %s", _e)

        # 7. Schedule & MQTT
        schedule_worker = ScheduleWorker(schedule_svc, control_svc, modbus_server=None, interval=1.0)
        
        mqtt_sub = MqttSubscriber(
            broker=settings.MQTT_BROKER, 
            port=settings.MQTT_PORT,
            schedule_service=schedule_svc,
            control_service=control_svc,
            username=settings.MQTT_USERNAME,
            password=settings.MQTT_PASSWORD,
            project_server_ids_provider=lambda: [
                project.server_id for project in project_svc.get_projects()
                if getattr(project, "server_id", None) is not None
            ],
        )
        
        # Start Threads
        build_tele_worker.mqtt_sub = mqtt_sub
        poll_worker.start()
        logic_worker.start()
        persist_worker.start()
        build_tele_worker.start()
        schedule_worker.start()
        evn_command_worker.start()
        ze_worker.start()
        mqtt_sub.connect()
        logger.info("ZeroExportWorker started.")
        
        logger.info("Polling Service operational. Press Ctrl+C to exit.")
        while True:
            time.sleep(10)

    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    except Exception as e:
        logger.error(f"Polling error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
