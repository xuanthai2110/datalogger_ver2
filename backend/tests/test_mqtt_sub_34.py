import os
import json
import time
import logging
import paho.mqtt.client as mqtt

# Thiết lập log cơ bản
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MQTT_Test_Sub_34")

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

# 1. Đọc cấu hình
env_config = load_env_vars()
broker = env_config.get("MQTT_BROKER", "14.224.236.53")
port = int(env_config.get("MQTT_PORT", 1883))
username = env_config.get("MQTT_USERNAME", "admin")
password = env_config.get("MQTT_PASSWORD", "@Dm!n")

topic = "telemetry/realtime/40"

# 2. Định nghĩa các callback của MQTT Client
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Kết nối thành công tới broker {broker}:{port}")
        client.subscribe(topic)
        logger.info(f"Đã đăng ký (subscribed) thành công vào topic: {topic}")
        logger.info("Đang đợi nhận dữ liệu realtime (mỗi 10 giây/lần)...")
    else:
        logger.error(f"Kết nối thất bại với mã lỗi: {rc}")

def on_message(client, userdata, msg):
    logger.info("=" * 60)
    logger.info(f"Nhận được message mới trên topic: {msg.topic}")
    try:
        payload_raw = msg.payload.decode("utf-8")
        payload_data = json.loads(payload_raw)
        
        # Định dạng JSON đẹp mắt để in ra màn hình
        formatted_json = json.dumps(payload_data, indent=4, ensure_ascii=False)
        print(formatted_json)
    except Exception as e:
        logger.error(f"Không thể giải mã dữ liệu JSON: {e}")
        print("Dữ liệu thô:", msg.payload)
    logger.info("=" * 60)

# 3. Khởi tạo MQTT Client
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

if username:
    client.username_pw_set(username, password)

# 4. Chạy vòng lặp lắng nghe
try:
    logger.info(f"Đang kết nối tới broker MQTT: {broker}:{port}...")
    client.connect(broker, port, keepalive=60)
    client.loop_forever()
except KeyboardInterrupt:
    logger.info("Đã dừng script test.")
except Exception as e:
    logger.error(f"Lỗi khi chạy MQTT Client: {e}")
