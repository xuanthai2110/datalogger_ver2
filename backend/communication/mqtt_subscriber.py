import json
import logging
from typing import Callable, Iterable, Optional

import paho.mqtt.client as mqtt
import time
from backend.services.schedule_service import ScheduleService
from backend.services.control_service import ControlService


logger = logging.getLogger(__name__)


class MqttSubscriber:
    def __init__(
        self,
        broker: str,
        port: int,
        schedule_service: ScheduleService,
        control_service: ControlService = None,
        project_id: int = None,
        username: str = None,
        password: str = None,
        project_server_ids_provider: Optional[Callable[[], Iterable[int]]] = None,
    ):
        self.broker = broker
        self.port = port
        self.schedule_service = schedule_service
        self.control_service = control_service
        self.project_id_filter = project_id
        self.username = username
        self.password = password
        self.project_server_ids_provider = project_server_ids_provider
        try:
            from paho.mqtt.enums import CallbackAPIVersion
            self.client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION1)
        except ImportError:
            self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.realtime_clients = {}

    def _get_subscription_topics(self):
        if self.project_id_filter is not None:
            return [
                f"controls/projects/{self.project_id_filter}/schedules/#",
                f"telemetry/realtime/enable/{self.project_id_filter}"
            ]

        if not self.project_server_ids_provider:
            return []

        try:
            server_ids = self.project_server_ids_provider() or []
        except Exception as e:
            logger.error(f"[MQTT] Failed to load project server_ids for subscription: {e}")
            return []

        topics = []
        seen = set()
        for server_id in server_ids:
            if server_id in (None, ""):
                continue
            try:
                normalized = int(server_id)
            except (TypeError, ValueError):
                logger.warning(f"[MQTT] Ignoring invalid project server_id for subscription: {server_id}")
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            topics.append(f"controls/projects/{normalized}/schedules/#")
            topics.append(f"telemetry/realtime/enable/{normalized}")
        return topics

    def connect(self):
        try:
            if self.username:
                self.client.username_pw_set(self.username, self.password)
            logger.info(f"[MQTT] Connecting to {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            logger.info(f"[MQTT] Loop started successfully for {self.broker}:{self.port}")
        except Exception as e:
            logger.error(f"[MQTT] Connection setup failed to {self.broker}:{self.port}: {e}", exc_info=True)

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic: str, payload: dict):
        try:
            self.client.publish(topic, json.dumps(payload), qos=0)
            logger.info(f"[MQTT] Published realtime payload to {topic}")
        except Exception as e:
            logger.error(f"[MQTT] Publish failed to {topic}: {e}")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            topics = self._get_subscription_topics()
            if not topics:
                logger.warning("[MQTT] No project server_id available, schedule subscriber did not subscribe to any topic.")
                return

            for topic in topics:
                self.client.subscribe(topic, qos=1)
                logger.info(f"[MQTT] Subscribed to {topic} with QoS 1")
        else:
            logger.error(f"[MQTT] Connect return code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            logger.info(f"[MQTT] Received message on topic: {topic}")
            
            if topic.startswith("telemetry/realtime/enable/"):
                logger.info(f"[MQTT] Processing realtime enable/disable message for topic: {topic}")
                try:
                    server_id = int(topic.split("/")[-1])
                    logger.info(f"[MQTT] Extracted server_id: {server_id}")
                except ValueError:
                    logger.warning(f"[MQTT] Invalid server_id in topic: {topic}")
                    return
                
                try:
                    payload_decoded = msg.payload.decode("utf-8")
                    logger.info(f"[MQTT] Payload raw content: {payload_decoded}")
                    payload = json.loads(payload_decoded)
                    status = payload.get("status")
                    client_id = payload.get("client_id")
                    logger.info(f"[MQTT] Parsed status: {status}, client_id: {client_id}")
                    
                    if status not in ("enable", "disable"):
                        logger.warning(f"[MQTT] Invalid status in payload: {status}")
                        return
                    
                    # Tìm project local theo server_id
                    projects = self.schedule_service.metadata_db.get_projects()
                    logger.info(f"[MQTT] List of projects in local DB: {[(p.id, p.server_id, p.telemetry_mode) for p in projects]}")
                    
                    project = next(
                        (p for p in projects if p.server_id is not None and str(p.server_id) == str(server_id)), 
                        None
                    )
                    if not project:
                        logger.warning(f"[MQTT] Project with server_id {server_id} not found in local DB.")
                        return
                    
                    # Cập nhật map realtime_clients
                    if server_id not in self.realtime_clients:
                        self.realtime_clients[server_id] = set()
                    
                    if status == "enable":
                        if client_id is not None:
                            self.realtime_clients[server_id].add(client_id)
                    else:
                        if client_id is not None:
                            self.realtime_clients[server_id].discard(client_id)
                        else:
                            self.realtime_clients[server_id].clear()
                    
                    logger.info(f"[MQTT] Current active client_ids for server_id {server_id}: {list(self.realtime_clients[server_id])}")
                    
                except Exception as e:
                    logger.error(f"[MQTT] Error handling realtime enable payload: {e}", exc_info=True)
                return

            payload = json.loads(msg.payload.decode("utf-8"))
            event = payload.get("event")
            schedule_data = payload.get("schedule") or {}
            schedule_id = schedule_data.get("id")

            if not event or schedule_id is None:
                return

            if event in ("schedule_created", "schedule_updated"):
                # Kiểm tra trạng thái local trước khi sync
                old_status = None
                existing = self.schedule_service.get(schedule_id)
                if existing:
                    old_status = existing.status

                # Đợi 2 giây để server kịp cập nhật dữ liệu trước khi GET (Tránh lỗi 404)
                time.sleep(2)
                project_server_id = schedule_data.get("project_id")
                synced = self.schedule_service.sync_schedule_from_server(schedule_id, project_server_id=project_server_id)
                
                # Nếu từ RUNNING chuyển sang CANCELED -> Reset ngay lập tức
                if synced and synced.status == "CANCELED" and old_status == "RUNNING":
                    if self.control_service:
                        self.control_service.reset(synced)

                if not synced:
                    logger.error(f"[MQTT] Failed to sync {event} for schedule {schedule_id}")
            elif event == "schedule_deleted":
                # Nếu lịch đang chạy mà bị xóa -> Reset ngay lập tức
                s = self.schedule_service.get(schedule_id)
                if s and s.status == "RUNNING":
                    if self.control_service:
                        self.control_service.reset(s)

                time.sleep(2)
                self.schedule_service.delete(schedule_id)

            logger.info(f"[MQTT] Processed {event} for schedule {schedule_id}")

        except Exception as e:
            logger.error(f"[MQTT] Event Parse Error: {e}")
