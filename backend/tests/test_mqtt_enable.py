import os
import sys
import time
import json
import logging
import paho.mqtt.client as mqtt

# Thiết lập đường dẫn gốc dự án
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.db_manager import MetadataDB, RealtimeDB
from backend.services.schedule_service import ScheduleService
from backend.communication.mqtt_subscriber import MqttSubscriber
from backend.core import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TestMqttEnable")

def test_mqtt_enable():
    # 1. Khởi tạo các DB và Service
    meta_db = MetadataDB(settings.METADATA_DB)
    realtime_db = RealtimeDB(settings.REALTIME_DB)
    schedule_svc = ScheduleService(realtime_db, meta_db)
    
    # Lấy dự án đầu tiên có server_id để test
    projects = meta_db.get_projects()
    test_project = None
    for p in projects:
        if p.server_id is not None:
            test_project = p
            break
            
    if not test_project:
        logger.error("Không tìm thấy dự án nào có server_id trong cơ sở dữ liệu để kiểm thử!")
        sys.exit(1)
        
    server_id = test_project.server_id
    project_id = test_project.id
    logger.info(f"Tìm thấy dự án kiểm thử: ID={project_id}, Name='{test_project.name}', Server ID={server_id}")
    
    # Đọc telemetry_mode ban đầu
    initial_mode = test_project.telemetry_mode or "Realtime"
    logger.info(f"Trạng thái telemetry_mode ban đầu trong DB: {initial_mode}")
    
    # 2. Khởi tạo MqttSubscriber lắng nghe sự kiện
    mqtt_sub = MqttSubscriber(
        broker=settings.MQTT_BROKER, 
        port=settings.MQTT_PORT,
        schedule_service=schedule_svc,
        username=settings.MQTT_USERNAME,
        password=settings.MQTT_PASSWORD,
        project_server_ids_provider=lambda: [server_id],
    )
    
    mqtt_sub.connect()
    time.sleep(2) # Đợi kết nối thành công và subscribe
    
    # 3. Tạo một client phụ để publish lệnh
    pub_client = mqtt.Client()
    if settings.MQTT_USERNAME:
        pub_client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    pub_client.connect(settings.MQTT_BROKER, settings.MQTT_PORT, 60)
    pub_client.loop_start()
    time.sleep(1)
    
    # --- TEST CASE 1: Gửi lệnh disable realtime ---
    logger.info("=== TEST CASE 1: Gửi disable realtime ===")
    topic = f"telemetry/realtime/enable/{server_id}"
    payload = {"status": "disable", "client_id": 99}
    logger.info(f"Publishing {payload} to {topic}...")
    pub_client.publish(topic, json.dumps(payload), qos=1)
    
    # Đợi MQTT xử lý
    time.sleep(3)
    
    # Kiểm tra xem client_id 99 đã bị xoá khỏi realtime_clients
    assert 99 not in mqtt_sub.realtime_clients.get(server_id, set()), "Thất bại: client_id 99 vẫn nằm trong realtime_clients"
    logger.info("TEST CASE 1 THÀNH CÔNG!")
    
    # --- TEST CASE 2: Gửi lệnh enable realtime ---
    logger.info("=== TEST CASE 2: Gửi enable realtime ===")
    payload = {"status": "enable", "client_id": 99}
    logger.info(f"Publishing {payload} to {topic}...")
    pub_client.publish(topic, json.dumps(payload), qos=1)
    
    # Đợi MQTT xử lý
    time.sleep(3)
    
    # Kiểm tra xem client_id 99 đã nằm trong realtime_clients
    assert 99 in mqtt_sub.realtime_clients.get(server_id, set()), "Thất bại: client_id 99 không nằm trong realtime_clients"
    logger.info("TEST CASE 2 THÀNH CÔNG!")
    
    # --- DỌN DẸP ---
    pub_client.loop_stop()
    pub_client.disconnect()
    mqtt_sub.disconnect()
    
    logger.info("TOÀN BỘ CÁC BÀI KIỂM THỬ ĐÃ THÀNH CÔNG!")

if __name__ == "__main__":
    test_mqtt_enable()
