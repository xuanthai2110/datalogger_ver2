import time
import requests
import logging
from backend.core.settings import API_BASE_URL
from backend.services.auth_service import AuthService

logger = logging.getLogger(__name__)

# Delay giữa mỗi HTTP request khi gửi outbox bù.
# Phòng ngừa server trả 429 (Too Many Requests) khi thiết bị gửi nhiều record liên tiếp
# sau một thời gian mất kết nối dài.
INTER_REQUEST_DELAY_S = 0.3


class UploaderService:
    def __init__(self, realtime_db, metadata_db):
        self.db = realtime_db
        self.metadata_db = metadata_db
        self.auth = AuthService(metadata_db)

    def upload(self):
        """
        Gửi tất cả record trong outbox lên server.

        Throttling: delay INTER_REQUEST_DELAY_S giữa mỗi request để tránh 429.
        Early exit: Nếu gặp 429 hoặc lỗi mạng, dừng vòng lặp ngay —
                    chu kỳ sau (5 phút) sẽ retry phần còn lại.
        """
        data_list = self.db.get_all_outbox()
        if not data_list:
            return

        total = len(data_list)
        if total > 1:
            logger.info(f"[Uploader] Starting upload of {total} records from outbox.")

        for idx, data in enumerate(data_list):
            should_continue = True
            try:
                project_id = data.get("project_id")
                server_id = data.get("server_id")
                if not project_id or not server_id:
                    continue

                # Look up server_account_id
                proj_meta = self.metadata_db.get_project(project_id)
                if not proj_meta or not proj_meta.server_account_id:
                    logger.warning(f"Project {project_id} has no server account. Skipping upload.")
                    continue

                token = self.auth.get_access_token(proj_meta.server_account_id)
                if not token:
                    continue

                data_type = data.get("data_type", "Project")
                payload = data.copy()
                payload.pop("id", None)
                payload.pop("project_id", None)
                payload.pop("server_id", None)
                payload.pop("data_type", None)
                payload.pop("timestamp", None)

                if data_type == "EVN":
                    url = f"{API_BASE_URL}/api/telemetry/evn/project/{server_id}"
                else:
                    url = f"{API_BASE_URL}/api/telemetry/project/{server_id}"

                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

                logger.info(f"[Uploader] [{idx+1}/{total}] Sending {data_type} for project {server_id} ...")
                response = requests.post(url, json=payload, headers=headers, timeout=15)

                # --- Xử lý 401: Refresh token và thử lại 1 lần ---
                if response.status_code == 401:
                    logger.warning(f"[Uploader] 401 Unauthorized for project {server_id}. Attempting token refresh...")
                    token = self.auth.handle_unauthorized(proj_meta.server_account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        response = requests.post(url, json=payload, headers=headers, timeout=15)
                        logger.info(f"[Uploader] Retry after 401 for project {server_id}: status={response.status_code}")

                # --- Xử lý 422: Fix payload và thử lại 1 lần ---
                if response.status_code == 422:
                    logger.warning(
                        f"[Uploader] 422 Validation error for record {data['id']} "
                        f"(project {server_id}). Attempting payload fix and retry..."
                    )
                    self._fix_payload_severity(payload)
                    response = requests.post(url, json=payload, headers=headers, timeout=15)
                    logger.info(f"[Uploader] Retry after 422 fix for record {data['id']}: status={response.status_code}")

                # --- Ra quyết định: DELETE/KEEP và kiểm tra có nên tiếp tục không ---
                should_continue = self._handle_response(response, data, server_id)

            except requests.exceptions.Timeout:
                logger.warning(
                    f"[Uploader] Request timeout for record {data.get('id')}. "
                    f"Keeping in outbox. Stopping current cycle."
                )
                should_continue = False  # Timeout = mạng đang yếu, không gửi tiếp

            except requests.exceptions.ConnectionError:
                logger.warning(
                    f"[Uploader] Connection error for record {data.get('id')}. "
                    f"Keeping in outbox. Stopping current cycle."
                )
                should_continue = False  # Mất mạng, không gửi tiếp

            except Exception as e:
                logger.error(f"[Uploader] Unexpected error for record {data.get('id')}: {e}")

            # --- Quyết định có tiếp tục không ---
            if not should_continue:
                remaining = total - idx - 1
                if remaining > 0:
                    logger.warning(
                        f"[Uploader] Upload cycle stopped early. "
                        f"{remaining} record(s) remaining in outbox — will retry next cycle."
                    )
                break

            # Throttle: delay giữa các request để tránh trigger rate limit của server.
            # Không cần delay sau record cuối cùng.
            if idx < total - 1:
                time.sleep(INTER_REQUEST_DELAY_S)

    def _handle_response(self, response: requests.Response, data: dict, server_id) -> bool:
        """
        Ra quyết định DELETE hoặc KEEP record trong outbox dựa trên HTTP status code.

        Return:
            True  — Tiếp tục gửi record tiếp theo.
            False — Dừng vòng lặp upload ngay lập tức (rate limit, mạng tạm lỗi).

        Chính sách:
            DELETE  — Khi server đã nhận data chắc chắn, hoặc xác nhận không bao giờ nhận.
            KEEP    — Khi lỗi có thể tự khỏi (mạng, server tạm lỗi) hoặc cần kỹ sư can thiệp.

        Nguyên tắc: Mất data LUÔN tệ hơn giữ record rác trong outbox.
        """
        status = response.status_code
        record_id = data["id"]

        # ── NHÓM DELETE: Server đã có data ──────────────────────────────────────
        if status in (200, 201, 204):
            self.db.delete_from_outbox(record_id)
            logger.info(f"[Uploader] SUCCESS ({status}): Uploaded record {record_id} for project {server_id}.")
            return True

        if status == 409:
            # Conflict — Data đã tồn tại trên server. Xóa là an toàn.
            self.db.delete_from_outbox(record_id)
            logger.warning(
                f"[Uploader] 409 Conflict for record {record_id} (project {server_id}). "
                f"Data already exists on server. Removed from outbox."
            )
            return True

        if status == 410:
            # Gone — Server xác nhận resource bị xóa vĩnh viễn, sẽ không bao giờ nhận.
            self.db.delete_from_outbox(record_id)
            logger.warning(
                f"[Uploader] 410 Gone for record {record_id} (project {server_id}). "
                f"Server resource permanently removed. Removed from outbox."
            )
            return True

        # ── NHÓM ABORT: Dừng vòng lặp ngay — gửi tiếp sẽ làm tệ hơn ──────────
        if status == 429:
            # Rate Limited — Server yêu cầu giảm tốc độ gửi.
            # Đọc Retry-After header nếu có để log cho kỹ sư biết.
            retry_after = response.headers.get("Retry-After")
            retry_msg = f" Server requests retry after {retry_after}s." if retry_after else ""
            logger.warning(
                f"[Uploader] 429 Rate Limited for record {record_id} (project {server_id})."
                f"{retry_msg} Keeping in outbox. Stopping current upload cycle."
            )
            return False  # ← Signal dừng vòng lặp ngay

        if 500 <= status < 600:
            # Server đang lỗi — gửi tiếp sẽ thất bại hết, không nên lãng phí CPU và mạng.
            logger.warning(
                f"[Uploader] {status} Server Error for record {record_id} (project {server_id}). "
                f"Keeping in outbox. Stopping current upload cycle."
            )
            return False  # ← Dừng luôn, server đang down

        # ── NHÓM KEEP + ERROR LOG: 4xx — Cần kỹ sư xem xét ────────────────────
        # 400 Bad Request  → Payload sai format (code bug), không tự khỏi.
        # 403 Forbidden    → Tài khoản không có quyền, có thể do cấu hình.
        # 404 Not Found    → server_id chưa tồn tại trên server, có thể chưa đồng bộ.
        # 408 Timeout      → Không chắc server đã nhận chưa.
        # 422 (still fail) → Đã fix payload nhưng vẫn lỗi, cần kỹ sư xem payload.
        # Mọi 4xx còn lại  → Giữ để không mất data. Tiếp tục record tiếp theo.
        if 400 <= status < 500:
            logger.error(
                f"[Uploader] {status} Client Error for record {record_id} (project {server_id}). "
                f"Keeping in outbox. Manual review may be required. "
                f"Server response: {response.text[:300]}"
            )
            return True  # Tiếp tục — các record khác không bị ảnh hưởng bởi record này

        # ── FALLBACK: Mọi status code không xác định → KEEP ────────────────────
        logger.warning(
            f"[Uploader] Unexpected status {status} for record {record_id} (project {server_id}). "
            f"Keeping in outbox. Response: {response.text[:200]}"
        )
        return True

    def _fix_payload_severity(self, obj):
        """Hàm đệ quy để sửa 'NORMAL' thành 'STABLE' trong payload telemetry."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "severity" and v == "NORMAL":
                    obj[k] = "STABLE"
                else:
                    self._fix_payload_severity(v)
        elif isinstance(obj, list):
            for item in obj:
                self._fix_payload_severity(item)

    def send_immediate(self, data: dict):
        project_id = data.get("project_id")
        server_id = data.get("server_id")
        if not project_id or not server_id:
            return

        proj_meta = self.metadata_db.get_project(project_id)
        if not proj_meta or not proj_meta.server_account_id:
            return

        token = self.auth.get_access_token(proj_meta.server_account_id)
        if not token:
            return

        data_type = data.get("data_type", "Project")
        payload = data.copy()
        payload.pop("project_id", None)
        payload.pop("server_id", None)
        payload.pop("data_type", None)
        payload.pop("timestamp", None)

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if data_type == "EVN":
            url = f"{API_BASE_URL}/api/telemetry/evn/project/{server_id}"
        else:
            url = f"{API_BASE_URL}/api/telemetry/project/{server_id}"

        try:
            logger.info(f"[Uploader] Sending IMMEDIATE {data_type} for project {server_id} ...")
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 401:
                logger.warning(f"[Uploader] Immediate 401 for project {server_id}. Refreshing token...")
                token = self.auth.handle_unauthorized(proj_meta.server_account_id)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = requests.post(url, json=payload, headers=headers, timeout=10)

            logger.info(f"[Uploader] Immediate result for project {server_id}: status={resp.status_code}")
        except requests.exceptions.Timeout:
            logger.warning(f"[Uploader] Immediate send timeout for project {server_id}.")
        except requests.exceptions.ConnectionError:
            logger.warning(f"[Uploader] Immediate send connection error for project {server_id}.")
        except Exception as e:
            logger.error(f"[Uploader] Immediate send error: {e}")
