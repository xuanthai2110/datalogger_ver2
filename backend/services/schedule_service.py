from typing import List, Optional
import logging
import time

import requests

from backend.core.settings import API_BASE_URL
from backend.db_manager.realtime import RealtimeDB
from backend.models.schedule import ControlScheduleCreate, ControlScheduleUpdate, ControlScheduleResponse
from backend.services.auth_service import AuthService


logger = logging.getLogger(__name__)


class ScheduleService:
    def __init__(self, db: RealtimeDB, metadata_db):
        self.db = db
        self.metadata_db = metadata_db
        self.auth = AuthService(metadata_db)
        self.fetch_retry_count = 5
        self.fetch_retry_delay_sec = 0.5

    def _remote_schedule_url(self, schedule_id: int) -> str:
        base = API_BASE_URL.rstrip("/")
        # Fix: sử dụng gạch ngang (-) thay vì gạch dưới (_) theo yêu cầu server
        return f"{base}/api/control-schedules/{schedule_id}"

    def _short_body(self, value, limit: int = 500) -> str:
        text = value if isinstance(value, str) else str(value)
        return text if len(text) <= limit else text[:limit] + "...<truncated>"

    def _resolve_account_id_from_project_ref(self, project_ref: Optional[int]) -> Optional[int]:
        if not project_ref:
            return None

        proj = self.metadata_db.get_project(project_ref)
        if proj and proj.server_account_id:
            return proj.server_account_id

        projects = self.metadata_db.get_projects()
        proj = next((p for p in projects if p.server_id == project_ref), None)
        if proj and proj.server_account_id:
            logger.info(
                "[ScheduleService] Resolved project_ref=%s via server_id -> local project_id=%s for auth",
                project_ref,
                proj.id,
            )
            return proj.server_account_id

        return None

    def _get_headers(self, project_id: Optional[int] = None, schedule_id: Optional[int] = None, project_server_id: Optional[int] = None) -> Optional[dict]:
        account_id = None
        if project_id:
            account_id = self._resolve_account_id_from_project_ref(project_id)
        elif project_server_id:
            account_id = self._resolve_account_id_from_project_ref(project_server_id)
        elif schedule_id:
            sched = self.db.get_schedule(schedule_id)
            if sched and sched.project_id:
                account_id = self._resolve_account_id_from_project_ref(sched.project_id)

        # Fallback to default account (1) if not found, but ideally it should be explicit
        if not account_id:
            logger.warning(
                "[ScheduleService] Could not resolve server account for project_id=%s schedule_id=%s project_server_id=%s. Falling back to account_id=1",
                project_id,
                schedule_id,
                project_server_id,
            )
            
        token = self.auth.get_access_token(account_id)
        if not token:
            logger.error(f"[ScheduleService] Cannot call server schedule API for account {account_id} because auth token is unavailable.")
            return None
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _build_local_schedule(self, remote_schedule: dict) -> ControlScheduleCreate:
        maxp_kw = remote_schedule.get("maxp_kw")
        limit_watts = remote_schedule.get("limit_watts")
        if limit_watts is None and maxp_kw is not None:
            limit_watts = float(maxp_kw) * 1000.0

        limit_percent = remote_schedule.get("limit_percent")
        if limit_percent is None:
            limit_percent = remote_schedule.get("percent")

        return ControlScheduleCreate(
            id=remote_schedule.get("id"),
            project_id=remote_schedule.get("project_id"),
            project_name=remote_schedule.get("project_name"),
            scope=remote_schedule.get("scope"),
            mode=remote_schedule.get("mode"),
            start_at=remote_schedule.get("start_at"),
            end_at=remote_schedule.get("end_at"),
            status=remote_schedule.get("status", "SCHEDULED"),
            inverter_id=remote_schedule.get("inverter_id"),
            serial_number=remote_schedule.get("serial_number"),
            limit_watts=limit_watts,
            limit_percent=limit_percent,
            hours=remote_schedule.get("hours"),
            day=remote_schedule.get("day"),
            created_at=remote_schedule.get("created_at"),
            updated_at=remote_schedule.get("updated_at"),
        )

    def get_all(self) -> List[ControlScheduleResponse]:
        return self.db.get_all_schedules()

    def get(self, schedule_id: int) -> Optional[ControlScheduleResponse]:
        return self.db.get_schedule(schedule_id)

    def create(self, data: ControlScheduleCreate) -> ControlScheduleResponse:
        logger.info(f"[ScheduleService] Creating schedule: {data}")
        return self.db.upsert_schedule(data, schedule_id=data.id)

    def update(self, schedule_id: int, data: ControlScheduleUpdate):
        logger.info(f"[ScheduleService] Updating schedule {schedule_id}")
        self.db.patch_schedule(schedule_id, data)

    def update_status(self, schedule_id: int, status: str, sync_remote: bool = False):
        logger.info(f"[ScheduleService] Updating status of schedule {schedule_id} to {status}")
        self.db.patch_schedule(schedule_id, ControlScheduleUpdate(status=status))
        if sync_remote:
            self.patch_remote_status(schedule_id, status)

    def delete(self, schedule_id: int):
        logger.info(f"[ScheduleService] Deleting schedule {schedule_id}")
        self.db.delete_schedule(schedule_id)

    def fetch_remote_schedule(self, schedule_id: int, project_server_id: Optional[int] = None) -> Optional[dict]:
        headers = self._get_headers(schedule_id=schedule_id, project_server_id=project_server_id)
        if not headers:
            return None

        url = self._remote_schedule_url(schedule_id)
        for attempt in range(1, self.fetch_retry_count + 1):
            logger.info("[ScheduleService] GET %s attempt=%s/%s", url, attempt, self.fetch_retry_count)
            try:
                response = requests.get(url, headers=headers, timeout=10)
                logger.info(
                    "[ScheduleService] GET %s -> status=%s body=%s",
                    url,
                    response.status_code,
                    self._short_body(response.text),
                )
                if response.status_code == 200:
                    return response.json()

                is_retryable_404 = response.status_code == 404 and attempt < self.fetch_retry_count
                if is_retryable_404:
                    logger.warning(
                        "[ScheduleService] Remote schedule %s not visible yet. Retrying in %.1fs...",
                        schedule_id,
                        self.fetch_retry_delay_sec,
                    )
                    time.sleep(self.fetch_retry_delay_sec)
                    continue

                logger.error(
                    "[ScheduleService] Fetch remote schedule %s failed (status=%s): %s",
                    schedule_id,
                    response.status_code,
                    response.text,
                )
                return None
            except Exception as e:
                if attempt < self.fetch_retry_count:
                    logger.warning(
                        "[ScheduleService] Fetch remote schedule %s attempt %s error: %s. Retrying in %.1fs...",
                        schedule_id,
                        attempt,
                        e,
                        self.fetch_retry_delay_sec,
                    )
                    time.sleep(self.fetch_retry_delay_sec)
                    continue
                logger.error(f"[ScheduleService] Fetch remote schedule {schedule_id} error: {e}")
                return None

    def sync_schedule_from_server(self, schedule_id: int, project_server_id: Optional[int] = None) -> Optional[ControlScheduleResponse]:
        remote_schedule = self.fetch_remote_schedule(schedule_id, project_server_id=project_server_id)
        if not remote_schedule:
            return None

        if remote_schedule.get("scope") == "INVERTER" and not remote_schedule.get("serial_number"):
            logger.error(
                "[ScheduleService] Remote inverter schedule %s has no serial_number; control will be rejected.",
                schedule_id,
            )

        local_schedule = self._build_local_schedule(remote_schedule)
        logger.info(f"[ScheduleService] Synced schedule {schedule_id} from server")
        return self.create(local_schedule)

    def patch_remote_status(self, schedule_id: int, status: str) -> bool:
        headers = self._get_headers(schedule_id=schedule_id)
        if not headers:
            return False

        url = self._remote_schedule_url(schedule_id)
        payload = {"status": status}
        logger.info("[ScheduleService] PATCH %s payload=%s", url, payload)
        try:
            response = requests.patch(url, json=payload, headers=headers, timeout=10)
            logger.info(
                "[ScheduleService] PATCH %s -> status=%s body=%s",
                url,
                response.status_code,
                self._short_body(response.text),
            )
            if response.status_code not in (200, 201):
                logger.error(
                    "[ScheduleService] Patch remote schedule %s -> %s failed (status=%s): %s",
                    schedule_id,
                    status,
                    response.status_code,
                    response.text,
                )
                return False
            logger.info(f"[ScheduleService] Patched remote schedule {schedule_id} -> {status}")
            return True
        except Exception as e:
            logger.error(f"[ScheduleService] Patch remote schedule {schedule_id} -> {status} error: {e}")
            return False

    def patch_remote_fields(self, schedule_id: int, payload: dict) -> bool:
        headers = self._get_headers(schedule_id=schedule_id)
        if not headers:
            return False

        url = self._remote_schedule_url(schedule_id)
        logger.info("[ScheduleService] PATCH fields %s payload=%s", url, payload)
        try:
            response = requests.patch(url, json=payload, headers=headers, timeout=10)
            logger.info(
                "[ScheduleService] PATCH fields %s -> status=%s body=%s",
                url,
                response.status_code,
                self._short_body(response.text),
            )
            if response.status_code not in (200, 201):
                logger.error(
                    "[ScheduleService] Patch remote schedule fields %s failed (status=%s): %s",
                    response.status_code,
                    response.text,
                    schedule_id,
                )
                return False
            logger.info(f"[ScheduleService] Patched remote schedule fields {schedule_id} successfully")
            return True
        except Exception as e:
            logger.error(f"[ScheduleService] Patch remote schedule fields {schedule_id} error: {e}")
            return False

    def has_active_p_schedule(self, project_id: int) -> bool:
        """Kiểm tra xem có lệnh điều khiển P (MAXP/PERCENT) nào đang active cho project không.
        
        Dùng bởi ZeroExportService để nhường quyền điều khiển cho Server/MQTT.
        ZeroExport sẽ tự resume khi không còn lệnh nào active.
        
        Args:
            project_id: ID project local (không phải server_id)
            
        Returns:
            True nếu có ít nhất 1 schedule P đang ở trạng thái EXECUTING/APPLIED/ACTIVE,
            False nếu không có lệnh nào đang chạy.
        """
        from datetime import datetime, timezone

        try:
            schedules = self.db.get_all_schedules()
            now_str = datetime.now(timezone.utc).isoformat()
            now = datetime.now(timezone.utc)

            for s in schedules:
                # Lọc theo project_id (local hoặc server_id)
                if s.project_id != project_id:
                    # Thử so với server_id
                    proj = self.metadata_db.get_project(project_id)
                    if not proj or s.project_id != proj.server_id:
                        continue

                # Chỉ quan tâm lệnh P
                if s.mode not in ("MAXP", "PERCENT", "LIMIT_PERCENT"):
                    continue

                # Kiểm tra trạng thái
                active_statuses = {"EXECUTING", "APPLIED", "ACTIVE", "RUNNING"}
                if s.status and s.status.upper() in active_statuses:
                    logger.debug(
                        "[ScheduleService] has_active_p_schedule: project=%s found active schedule id=%s mode=%s status=%s",
                        project_id, s.id, s.mode, s.status,
                    )
                    return True

                # Kiểm tra theo thời gian (status=SCHEDULED nhưng đang trong khoảng thời gian)
                if s.status and s.status.upper() == "SCHEDULED" and s.start_at and s.end_at:
                    try:
                        start = datetime.fromisoformat(s.start_at.replace("Z", "+00:00"))
                        end = datetime.fromisoformat(s.end_at.replace("Z", "+00:00"))
                        if start <= now <= end:
                            logger.debug(
                                "[ScheduleService] has_active_p_schedule: project=%s schedule id=%s is time-active (%s to %s)",
                                project_id, s.id, s.start_at, s.end_at,
                            )
                            return True
                    except Exception:
                        pass

            return False

        except Exception as e:
            logger.error("[ScheduleService] has_active_p_schedule error for project %s: %s", project_id, e)
            return False  # An toàn: nếu lỗi, cho ZE chạy bình thường

