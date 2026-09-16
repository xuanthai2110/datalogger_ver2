import os
import sys
import json
import time
import logging
import paho.mqtt.client as mqtt

# Thiết lập log cơ bản
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MQTT_Test_Pub")

def load_env_vars():
    """Đọc file .env thủ công để lấy cấu hình MQTT."""
    env = {}
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    parts = line.split("=", 1)
                    k = parts[0].strip()
                    v = parts[1].strip()
                    # Loại bỏ dấu nháy nếu có
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    env[k] = v
    return env

def main():
    # 1. Đọc cấu hình từ .env hoặc mặc định
    env_config = load_env_vars()
    broker = env_config.get("MQTT_BROKER", "14.224.236.53")
    port = int(env_config.get("MQTT_PORT", 1883))
    username = env_config.get("MQTT_USERNAME", "admin")
    password = env_config.get("MQTT_PASSWORD", "@Dm!n")

    # Mặc định server_id là 34 và status là enable
    server_id = 34
    status = "enable"

    # Hỗ trợ truyền tham số dòng lệnh: python test_mqtt_pub.py [server_id] [status: enable/disable]
    if len(sys.argv) > 1:
        try:
            server_id = int(sys.argv[1])
        except ValueError:
            logger.error("Server ID truyền vào phải là một số nguyên!")
            sys.exit(1)
            
    if len(sys.argv) > 2:
        status = sys.argv[2].lower()
        if status not in ("enable", "disable"):
            logger.error("Trạng thái (status) phải là 'enable' hoặc 'disable'!")
            sys.exit(1)

    topic = f"telemetry/realtime/enable/{server_id}"
    payload = {"status": status}

    # 2. Khởi tạo MQTT Client và kết nối
    client = mqtt.Client()
    if username:
        client.username_pw_set(username, password)

    try:
        logger.info(f"Đang kết nối tới broker MQTT: {broker}:{port}...")
        client.connect(broker, port, keepalive=60)
        
        # Chạy loop ngầm để đảm bảo gửi tin nhắn thành công
        client.loop_start()
        time.sleep(1)

        # 3. Publish dữ liệu
        logger.info(f"Gửi bản tin điều khiển tới topic: {topic}")
        logger.info(f"Payload: {json.dumps(payload)}")
        
        info = client.publish(topic, json.dumps(payload), qos=1)
        info.wait_for_publish() # Đợi xác nhận gửi thành công từ Broker
        
        logger.info("Gửi bản tin thành công!")
        
        # Dừng loop và ngắt kết nối
        time.sleep(0.5)
        client.loop_stop()
        client.disconnect()
        logger.info("Đã đóng kết nối MQTT.")

    except Exception as e:
        logger.error(f"Gặp lỗi khi gửi bản tin MQTT: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
