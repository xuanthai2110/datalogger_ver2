import requests
import logging
import time
from typing import Optional, List, Dict
from datetime import datetime, timezone
from dataclasses import asdict
from backend.core.settings import API_BASE_URL
from backend.models.project import ProjectCreate, ProjectUpdate
from backend.models.inverter import InverterCreate, InverterUpdate

logger = logging.getLogger(__name__)

# Global set để chống spam tạo nhiều tiến trình ngầm theo dõi cùng 1 request
_ACTIVE_POLLS = set()

class SetupService:
    def __init__(self, auth_service, project_service):
        self.auth = auth_service
        self.project_svc = project_service

    def login(self, account_id: int) -> bool:
        """Thực hiện đăng nhập cho một tài khoản server cụ thể."""
        token = self.auth.get_access_token(account_id, force_refresh=True)
        return token is not None

    @staticmethod
    def _is_equal(a, b):
        """So sánh thông minh giữa dữ liệu local và server."""
        if a == b: return True
        try:
            if float(a) == float(b): return True
        except (TypeError, ValueError):
            pass
        a_str = "" if a is None else str(a).strip()
        b_str = "" if b is None else str(b).strip()
        return a_str == b_str

    def scan_inverters(self, transport, project_id: int, driver_class) -> list[int]:
        """
        QUY TRÌNH QUÉT INVERTER:
        1. Lặp qua dải Slave ID (mặc định 1-30).
        2. Với mỗi ID, khởi tạo driver và thử đọc thông tin (read_info).
        3. Nếu inverter phản hồi (is_active), gán project_id và số thứ tự (inverter_index).
        4. Lưu thông tin vào Database local (upsert_inverter).
        """
        found_ids = []
        logger.info(f"[Setup] Starting scan for inverters (Slave 1-30) using {driver_class.__name__}")
        
        for slave_id in range(1, 31):
            success = False
            for attempt in range(2):
                try:
                    driver = driver_class(transport, slave_id=slave_id)
                    info = driver.read_info()
                    
                    if info and info.get("is_active"):
                        logger.info(f"[Setup] Found active inverter at Slave ID {slave_id}: {info['serial_number']}")
                        inv_data = InverterCreate(**info)
                        local_id = self.project_svc.upsert_inverter(inv_data)
                        found_ids.append(local_id)
                        success = True
                        break
                    else:
                        logger.debug(f"[Setup] No active inverter at Slave ID {slave_id} (Attempt {attempt+1})")
                except Exception as e:
                    logger.debug(f"[Setup] Error scanning Slave ID {slave_id} (Attempt {attempt+1}): {e}")
                
                if not success and attempt == 0:
                    time.sleep(1) # Delay 1s before retry
                    
        logger.info(f"[Setup] Scan complete. Found {len(found_ids)} inverters.")
        return found_ids

    def scan_batteries(self, transport, project_id: int, driver_class, slave_start: int = 1, slave_end: int = 30) -> list[int]:
        """
        QUY TRÌNH QUÉT BATTERY (BMS DIRECT SCAN):
        1. Lặp qua dải Slave ID (slave_start -> slave_end).
        2. Với mỗi Slave ID, dùng BMS driver thử đọc thông tin phần cứng (`read_info`).
        3. Nếu BMS phản hồi (`is_active` & `serial_number`), gán `project_id`.
        4. Lưu thông tin vào Database local (`upsert_battery`).
        """
        from backend.models.battery import BatteryCreate
        from dataclasses import fields
        found_ids = []
        logger.info(f"[Setup] Starting scan for batteries (Slave {slave_start}-{slave_end}) using {driver_class.__name__}")
        
        for slave_id in range(slave_start, slave_end + 1):
            success = False
            for attempt in range(2):
                try:
                    driver = driver_class(transport, slave_id=slave_id)
                    info = driver.read_info()
                    
                    if info and info.get("serial_number"):
                        logger.info(f"[Setup] Found active battery at Slave ID {slave_id}: {info['serial_number']} ({info.get('brand')} {info.get('model')})")
                        info["project_id"] = project_id
                        info["battery_index"] = len(found_ids) + 1
                        
                        valid_fields = {f.name for f in fields(BatteryCreate)}
                        filtered = {k: v for k, v in info.items() if k in valid_fields}
                        
                        batt_res = self.project_svc.upsert_battery(BatteryCreate(**filtered))
                        found_ids.append(batt_res.id)
                        success = True
                        break
                    else:
                        logger.debug(f"[Setup] No battery response at Slave ID {slave_id} (Attempt {attempt+1})")
                except Exception as e:
                    logger.debug(f"[Setup] Error scanning Battery Slave ID {slave_id} (Attempt {attempt+1}): {e}")
                
                if not success and attempt == 0:
                    time.sleep(0.5)
                    
        logger.info(f"[Setup] Battery scan complete. Found {len(found_ids)} batteries.")
        return found_ids

    def _get_token_for_project(self, project_id: int) -> tuple[Optional[str], Optional[int]]:
        """Lấy token và account_id cho project."""
        project = self.project_svc.get_project(project_id)
        if not project or not project.server_account_id:
            logger.warning(f"[Sync] Project {project_id} has no server_account_id.")
            return None, None
            
        token = self.auth.get_access_token(project.server_account_id)
        return token, project.server_account_id

    def pre_sync_check(self, project_id: int) -> bool:
        """Kiểm tra dự án trên server bằng elec_meter_no (format mới)."""
        local_project = self.project_svc.get_project(project_id)
        logger.info(f"[Sync] Starting pre_sync_check for project {project_id} (Meter: {local_project.elec_meter_no if local_project else 'None'})")
        
        if not local_project or not local_project.elec_meter_no:
            logger.info(f"[Sync] Pre-sync: Missing project or elec_meter_no.")
            return False
            
        if local_project.server_id:
            logger.info(f"[Sync] Pre-sync: Project already has server_id {local_project.server_id}. Skipping search.")
            return False

        token, account_id = self._get_token_for_project(project_id)
        if not token: 
            logger.info(f"[Sync] Pre-sync: No access token available.")
            return False

        try:
            base_api = API_BASE_URL.rstrip('/')
            # Thử với telemetry=true theo yêu cầu mới nhất của bạn để tìm dự án đã chạy
            url = f"{base_api}/api/projects/?telemetry=true&page=1&limit=20&search={local_project.elec_meter_no}&search_fields=elec_meter_no"
            logger.info(f"[Sync] Pre-sync URL: {url}")
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 401:
                logger.info("[Sync] Pre-sync: 401 detected, attempting to recover...")
                token = self.auth.handle_unauthorized(account_id)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code != 200:
                logger.warning(f"[Sync] Pre-sync: Server returned {resp.status_code}")
                return False

            raw_response = resp.json()
            logger.info(f"[Sync] Pre-sync search response for {local_project.elec_meter_no}: {raw_response}")
            
            data_items = raw_response.get("data", [])
            matched_proj_data = None
            
            for item in data_items:
                # Thử lấy từ key 'project' nếu có (với các endpoint trả về bundle) hoặc lấy trực tiếp item
                p_info = item.get("project", item)
                if str(p_info.get("elec_meter_no")) == str(local_project.elec_meter_no):
                    matched_proj_data = p_info
                    break
            
            if matched_proj_data:
                server_proj_id = matched_proj_data.get("id")
                if server_proj_id:
                    self.project_svc.update_project_sync(project_id, server_id=server_proj_id, status='approved')
                    logger.info(f"[Sync] Auto-matched project {project_id} -> Server ID {server_proj_id}")
                
                # 2. Thử so khớp Inverters của project này
                # Giả định server có endpoint lấy inverters hoặc lọc theo project_id server
                inv_url = f"{base_api}/api/inverters/?telemetry=false" # Lấy hết hoặc thêm filter nếu server hỗ trợ
                inv_resp = requests.get(inv_url, headers=headers, timeout=10)
                if inv_resp.status_code == 200:
                    server_invs = inv_resp.json().get("data", [])
                    local_invs = self.project_svc.get_inverters_by_project(project_id)
                    
                    for li in local_invs:
                        for si_item in server_invs:
                            si = si_item.get("inverter", si_item) # Support both nested and flat
                            if si.get("serial_number") == li.serial_number:
                                self.project_svc.update_inverter_sync(li.id, server_id=si.get("id"), status='approved')
                                logger.info(f"[Sync] Auto-matched inverter {li.serial_number} -> Server ID {si.get('id')}")
                                break
                
                return True
        except Exception as e:
            logger.error(f"[Sync] Pre-sync error: {e}")
        
        return False

    def initiate_project_sync(self, project_id: int) -> Optional[int]:
        """Gửi yêu cầu đồng bộ Project (POST /api/projects/requests/)"""
        project = self.project_svc.get_project(project_id)
        if not project: return None

        token, account_id = self._get_token_for_project(project_id)
        if not token: return None

        # Danh sách các trường Project theo yêu cầu server
        project_fields = {
            'elec_meter_no', 'elec_price_per_kwh', 'name', 'location', 
            'lat', 'lon', 'capacity_kwp', 'ac_capacity_kw', 'inverter_count'
        }
        payload = {k: v for k, v in asdict(project).items() if k in project_fields}

        try:
            base_api = API_BASE_URL.rstrip('/')
            url = f"{base_api}/api/projects/requests/"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            # 0. Nếu dự án ĐÃ ĐƯỢC DUYỆT, ta dùng POST update với full payload
            if project.server_id and project.sync_status == 'approved':
                # KIỂM TRA SỰ THAY ĐỔI
                check_url = f"{base_api}/api/projects/{project.server_id}"
                get_resp = requests.get(check_url, headers=headers, timeout=10)
                if get_resp.status_code == 401:
                    token = self.auth.handle_unauthorized(account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        get_resp = requests.get(check_url, headers=headers, timeout=10)
                
                diff_payload = payload
                if get_resp.status_code == 200:
                    server_data = get_resp.json()
                    diff_payload = {}
                    for k, v in payload.items():
                        sv = server_data.get(k)
                        if not self._is_equal(sv, v):
                            diff_payload[k] = v
                    if not diff_payload:
                        logger.info(f"[Sync] Project {project_id} has no changes. Skipping POST update.")
                        return -1
                        
                update_url = f"{base_api}/api/projects/requests/update/{project.server_id}"
                logger.info(f"[Sync] Project is approved. Sending update request to {update_url} with: {diff_payload}")
                resp = requests.post(update_url, json=diff_payload, headers=headers, timeout=20)
                
                if resp.status_code == 401:
                    token = self.auth.handle_unauthorized(account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        resp = requests.post(update_url, json=diff_payload, headers=headers, timeout=20)
                
                if resp.status_code in [200, 201, 202]:
                    res_data = resp.json()
                    request_id = res_data.get("id")
                    if request_id:
                        # Giữ trạng thái 'approved' - Chỉ cập nhật server_request_id để track
                        self.project_svc.update_project_sync(project_id, server_request_id=request_id, status='approved')
                        return request_id
                else:
                    logger.warning(f"[Sync] Project update request failed: {resp.status_code} - {resp.text}")
                return None

            # 1. Thử PATCH nếu đang ở trạng thái pending
            if project.server_request_id:
                req_url = f"{base_api}/api/projects/requests/{project.server_request_id}"
                check_resp = requests.get(req_url, headers=headers, timeout=10)
                
                if check_resp.status_code == 401:
                    token = self.auth.handle_unauthorized(account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        check_resp = requests.get(req_url, headers=headers, timeout=10)
                
                if check_resp.status_code == 200:
                    server_data = check_resp.json()
                    status = server_data.get("status", "").lower()
                    
                    if status == "pending":
                        patch_payload = {}
                        for k, v in payload.items():
                            if not self._is_equal(server_data.get(k), v):
                                patch_payload[k] = v
                        
                        if not patch_payload:
                            logger.info(f"[Sync] Project {project_id} has no changes to patch.")
                            return project.server_request_id
                        
                        logger.info(f"[Sync] Patching project request {project.server_request_id} with: {patch_payload}")
                        patch_resp = requests.patch(req_url, json=patch_payload, headers=headers, timeout=20)
                        
                        if patch_resp.status_code == 401:
                            token = self.auth.handle_unauthorized(account_id)
                            if token:
                                headers["Authorization"] = f"Bearer {token}"
                                patch_resp = requests.patch(req_url, json=patch_payload, headers=headers, timeout=20)
                        
                        if patch_resp.status_code in [200, 201, 202]:
                            return project.server_request_id
                        elif patch_resp.status_code == 403:
                            logger.info(f"[Sync] Project request {project.server_request_id} is locked by Admin. Cannot patch. Returning current ID.")
                            return project.server_request_id
                        else:
                            logger.warning(f"[Sync] Project patch failed: {patch_resp.status_code} - {patch_resp.text}")
                            return None
                    else:
                        if status == "approved":
                            server_id = server_data.get("server_id")
                            self.project_svc.update_project_sync(project_id, server_id=server_id, status='approved')
                            logger.info(f"[Sync] Project request {project.server_request_id} already approved on server. Verifying changes...")
                            return self.initiate_project_sync(project_id)
                        elif status == "rejected":
                            # Nếu đã bị từ chối, cho phép gửi yêu cầu mới hoàn toàn
                            logger.info(f"[Sync] Project request {project.server_request_id} was rejected. Allowing re-submission.")
                            self.project_svc.update_project_sync(project_id, server_request_id=0)
                            # Không return ở đây để code chạy xuống bước 2 (POST mới)
                        else:
                            logger.info(f"[Sync] Project request {project.server_request_id} is '{status}'. Cannot patch.")
                        
            # 2. Tạo mới bằng POST nếu chưa có

            resp = requests.post(url, json=payload, headers=headers, timeout=20)
            
            if resp.status_code == 401:
                logger.info("[Sync] Project: 401 detected, attempting to recover...")
                token = self.auth.handle_unauthorized(account_id)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = requests.post(url, json=payload, headers=headers, timeout=20)
                    
            if resp.status_code == 409:
                logger.info(f"[Sync] Project 409 Conflict. Searching with elec_meter_no: {project.elec_meter_no}")
                chk_url = f"{base_api}/api/projects/?telemetry=false&search={project.elec_meter_no}&search_fields=elec_meter_no"
                real_resp = requests.get(chk_url, headers=headers, timeout=10)
                if real_resp.status_code == 200:
                    data = real_resp.json().get("data", [])
                    if data:
                        # Lấy cái đầu tiên tìm thấy
                        rp = data[0].get("project", data[0])
                        logger.info(f"[Sync] Found existing project {rp.get('id')}. Auto-approving.")
                        self.project_svc.update_project_sync(project_id, server_id=rp.get("id"), status='approved')
                        return rp.get("id")
                logger.warning("[Sync] Project 409 Conflict but matching project not found via search API.")
                return None

            if resp.status_code in [200, 201, 202]:
                res_data = resp.json()
                request_id = res_data.get("id")
                if request_id:
                    self.project_svc.update_project_sync(project_id, server_request_id=request_id, status='pending')
                    return request_id
            else:
                logger.warning(f"[Sync] Project sync failed with status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"[Sync] Project sync error: {e}")
        
        return None

    def initiate_inverter_sync(self, inverter_id: int) -> Optional[int]:
        """Gửi yêu cầu đồng bộ Inverter (POST /api/inverters/requests/)"""
        inverter = self.project_svc.get_inverter_by_id(inverter_id)
        if not inverter: return None
        
        project_id = inverter.project_id
        token, account_id = self._get_token_for_project(project_id)
        if not token: return None

        sync_info = self.project_svc.metadata_db.get_project_sync_info(project_id)
        if not sync_info: return None

        # Danh sách các trường Inverter theo yêu cầu server
        inv_fields = {
            'inverter_index', 'serial_number', 'brand', 'model', 'firmware_version',
            'phase_count', 'mppt_count', 'string_count', 'rate_dc_kwp', 'rate_ac_kw',
            'is_active', 'replaced_by_id', 'usage_start_at', 'usage_end_at'
        }
        payload = {k: v for k, v in asdict(inverter).items() if k in inv_fields}
        
        # Server expects integer for these kw fields
        if payload.get('rate_dc_kwp') is not None:
            payload['rate_dc_kwp'] = int(round(float(payload['rate_dc_kwp'])))
        if payload.get('rate_ac_kw') is not None:
            payload['rate_ac_kw'] = int(round(float(payload['rate_ac_kw'])))
        
        # Thêm các ID liên kết (Chỉ chọn 1 trong 2 theo yêu cầu server)
        server_id = sync_info.get("server_id")
        server_req_id = sync_info.get("server_request_id")
        
        if server_id:
            payload["project_id"] = server_id
        elif server_req_id:
            payload["project_request_id"] = server_req_id
        else:
            logger.warning(f"[Sync] Project {project_id} has neither server_id nor server_request_id. Inverter sync will fail.")
            # Trường hợp 3: dự án chưa có cả 2 -> thông báo tạo request cho project trước
            return -2
        
        # Format date strings if they are objects
        if payload.get("usage_start_at") is None:
            payload["usage_start_at"] = datetime.now(timezone.utc).isoformat()

        try:
            base_api = API_BASE_URL.rstrip('/')
            url = f"{base_api}/api/inverters/requests/"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            # 0. Nếu inverter ĐÃ ĐƯỢC DUYỆT hoặc BỊ TỪ CHỐI CẬP NHẬT, ta gửi Request Update thay vì sửa trực tiếp
            if inverter.server_id and inverter.sync_status in ['approved', 'rejected']:
                # KIỂM TRA SỰ THAY ĐỔI
                check_url = f"{base_api}/api/inverters/{inverter.server_id}"
                get_resp = requests.get(check_url, headers=headers, timeout=10)
                if get_resp.status_code == 401:
                    token = self.auth.handle_unauthorized(account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        get_resp = requests.get(check_url, headers=headers, timeout=10)
                        
                if get_resp.status_code == 200:
                    server_data = get_resp.json()
                    logger.info(f"[Sync] Data from Server: {server_data}")
                    logger.info(f"[Sync] Data from Local (to compare): {payload}")
                    
                    if server_data.get("usage_start_at"):
                        payload["usage_start_at"] = server_data.get("usage_start_at")
                    if server_data.get("usage_end_at"):
                        payload["usage_end_at"] = server_data.get("usage_end_at")
                        
                    has_changes = False
                    for k, v in payload.items():
                        if k in ["project_id", "project_request_id"]:
                            continue
                        if not self._is_equal(server_data.get(k), v):
                            has_changes = True
                            break
                            
                    if not has_changes:
                        logger.info(f"[Sync] Inverter {inverter_id} has no changes. Skipping update request.")
                        return -1
                
                # Chuẩn bị full payload gửi lên (loại bỏ liên kết project)
                update_payload = payload.copy()
                update_payload.pop("project_id", None)
                update_payload.pop("project_request_id", None)
                
                update_url = f"{base_api}/api/inverters/requests/update/{inverter.server_id}"
                logger.info(f"[Sync] Sending Inverter Update Request (Full Payload) to {update_url}: {update_payload}")
                resp = requests.post(update_url, json=update_payload, headers=headers, timeout=20)
                
                if resp.status_code == 401:
                    token = self.auth.handle_unauthorized(account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        resp = requests.post(update_url, json=update_payload, headers=headers, timeout=20)
                
                if resp.status_code in [200, 201]:
                    new_req_id = resp.json().get("id")
                    if new_req_id:
                        self.project_svc.update_inverter_sync(inverter_id, server_request_id=new_req_id, status='pending')
                        logger.info(f"[Sync] Inverter update request created: {new_req_id}")
                        return new_req_id
                
                logger.warning(f"[Sync] Inverter Update Request failed: {resp.status_code} - {resp.text}")
                return None

            # 1. Nếu đang ở trạng thái pending (đã có request chưa xử lý)
            if inverter.server_request_id and inverter.sync_status == 'pending':
                req_url = f"{base_api}/api/inverters/requests/{inverter.server_request_id}"
                check_resp = requests.get(req_url, headers=headers, timeout=10)
                
                if check_resp.status_code == 401:
                    token = self.auth.handle_unauthorized(account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        check_resp = requests.get(req_url, headers=headers, timeout=10)
                        
                if check_resp.status_code == 200:
                    server_data = check_resp.json()
                    status = server_data.get("status", "").lower()
                    
                    if status == "pending":
                        logger.info(f"[Sync] Inverter request {inverter.server_request_id} is still pending. Blocking new update.")
                        return -99  # Trả về code đặc biệt để nhắc gọi điện
                    elif status == "approved":
                        server_id = server_data.get("approved_inverter_id") or server_data.get("target_inverter_id")
                        self.project_svc.update_inverter_sync(inverter_id, server_id=server_id, status='approved')
                        logger.info(f"[Sync] Inverter request {inverter.server_request_id} already approved. Re-verifying...")
                        return self.initiate_inverter_sync(inverter_id)
                    elif status == "rejected":
                        logger.info(f"[Sync] Inverter request {inverter.server_request_id} was rejected. Allowing re-submission.")
                        self.project_svc.update_inverter_sync(inverter_id, server_request_id=0, status='rejected')
                        return self.initiate_inverter_sync(inverter_id)
                else:
                    logger.warning(f"[Sync] Failed to check pending request {inverter.server_request_id}: {check_resp.status_code}")
                    return None

            # 2. Tạo mới bằng POST nếu chưa có (Create Request)
            logger.info(f"[Sync] Sending Inverter Create Request to {url}: {payload}")
            resp = requests.post(url, json=payload, headers=headers, timeout=20)
            
            if resp.status_code == 401:
                logger.info("[Sync] Inverter: 401 detected, attempting to recover...")
                token = self.auth.handle_unauthorized(account_id)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = requests.post(url, json=payload, headers=headers, timeout=20)
                    
            if resp.status_code == 409:
                logger.info(f"[Sync] Inverter 409 Conflict. Searching with SN: {inverter.serial_number}")
                chk_url = f"{base_api}/api/inverters/?telemetry=false&search={inverter.serial_number}&search_fields=serial_number"
                real_resp = requests.get(chk_url, headers=headers, timeout=10)
                if real_resp.status_code == 200:
                    data = real_resp.json().get("data", [])
                    if data:
                        ri = data[0].get("inverter", data[0])
                        logger.info(f"[Sync] Found existing inverter {ri.get('id')}. Auto-approving.")
                        self.project_svc.update_inverter_sync(inverter_id, server_id=ri.get("id"), status='approved')
                        return ri.get("id")
                logger.warning("[Sync] Inverter 409 Conflict but matching inverter not found via search API.")
                return None

            if resp.status_code in [200, 201, 202]:
                res_data = resp.json()
                request_id = res_data.get("id")
                if request_id:
                    self.project_svc.update_inverter_sync(inverter_id, server_request_id=request_id, status='pending')
                    return request_id
            else:
                logger.warning(f"[Sync] Inverter sync failed with status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"[Sync] Inverter sync error: {e}")
        
        return None

    def background_poll_status(self, request_id: int, project_id: int):
        """Theo dõi trạng thái phê duyệt từ Admin."""
        poll_key = f"proj_{request_id}"
        if poll_key in _ACTIVE_POLLS:
            return
            
        _ACTIVE_POLLS.add(poll_key)
        try:
            for _ in range(120):
                token, _ = self._get_token_for_project(project_id)
                if not token: 
                    time.sleep(60)
                    continue

                try:
                    url = f"{API_BASE_URL.rstrip('/')}/api/projects/requests/{request_id}"
                    headers = {"Authorization": f"Bearer {token}"}
                    resp = requests.get(url, headers=headers, timeout=10)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status", "").lower()
                        
                        if status == "approved":
                            s_id = data.get("approved_project_id") or data.get("target_project_id")
                            self.project_svc.update_project_sync(project_id, server_id=s_id, status='approved')
                            
                            inv_map = data.get("inverter_map", {})
                            for li in self.project_svc.get_inverters_by_project(project_id):
                                s_inv_id = inv_map.get(li.serial_number)
                                if s_inv_id:
                                    self.project_svc.update_inverter_sync(li.id, server_id=s_inv_id, status='approved')
                            
                            logger.info(f"[Sync] Project {project_id} APPROVED by Admin.")
                            break
                        elif status == "rejected":
                            self.project_svc.update_project_sync(project_id, status='rejected')
                            break
                except Exception as e:
                    logger.error(f"[Sync] Polling error: {e}")
                
                time.sleep(60)
        finally:
            _ACTIVE_POLLS.discard(poll_key)

    def background_poll_inverter_status(self, request_id: int, inverter_id: int):
        """Theo dõi trạng thái phê duyệt từ Admin cho Inverter."""
        poll_key = f"inv_{request_id}"
        if poll_key in _ACTIVE_POLLS:
            return
            
        _ACTIVE_POLLS.add(poll_key)
        try:
            for _ in range(120):
                # We need project_id for token
                inverter = self.project_svc.get_inverter_by_id(inverter_id)
                if not inverter: break
                token, _ = self._get_token_for_project(inverter.project_id)
                if not token:
                    time.sleep(60)
                    continue

                try:
                    url = f"{API_BASE_URL.rstrip('/')}/api/inverters/requests/{request_id}"
                    headers = {"Authorization": f"Bearer {token}"}
                    resp = requests.get(url, headers=headers, timeout=10)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status", "").lower()
                        
                        if status == "approved":
                            s_id = data.get("approved_inverter_id") or data.get("target_inverter_id")
                            self.project_svc.update_inverter_sync(inverter_id, server_id=s_id, status='approved')
                            logger.info(f"[Sync] Inverter {inverter_id} APPROVED by Admin.")
                            break
                        elif status == "rejected":
                            self.project_svc.update_inverter_sync(inverter_id, status='rejected')
                            break
                except Exception as e:
                    logger.error(f"[Sync] Polling inverter error: {e}")
                
                time.sleep(60)
        finally:
            _ACTIVE_POLLS.discard(poll_key)

    def request_delete_project_sync(self, project_id: int) -> bool:
        """Gửi yêu cầu xoá Project lên server (POST /api/projects/requests/delete/{server_id})"""
        project = self.project_svc.get_project(project_id)
        if not project or not project.server_id:
            return True

        token, account_id = self._get_token_for_project(project_id)
        if not token: return False

        try:
            base_api = API_BASE_URL.rstrip('/')
            url = f"{base_api}/api/projects/requests/delete/{project.server_id}"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            resp = requests.post(url, headers=headers, timeout=20)
            if resp.status_code == 401:
                token = self.auth.handle_unauthorized(account_id)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = requests.post(url, headers=headers, timeout=20)
            
            if resp.status_code in [200, 201, 202, 204]:
                logger.info(f"[Sync] Sent delete request for project {project_id} (Server ID {project.server_id})")
                return True
            else:
                logger.warning(f"[Sync] Project delete request failed: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"[Sync] Project delete sync error: {e}")
            return False

    def request_delete_inverter_sync(self, inverter_id: int) -> bool:
        """Gửi yêu cầu xoá Inverter lên server (POST /api/inverters/requests/delete/{server_id})"""
        inverter = self.project_svc.get_inverter_by_id(inverter_id)
        if not inverter or not inverter.server_id:
            return True

        token, account_id = self._get_token_for_project(inverter.project_id)
        if not token: return False

        try:
            base_api = API_BASE_URL.rstrip('/')
            url = f"{base_api}/api/inverters/requests/delete/{inverter.server_id}"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            resp = requests.post(url, headers=headers, timeout=20)
            if resp.status_code == 401:
                token = self.auth.handle_unauthorized(account_id)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = requests.post(url, headers=headers, timeout=20)
            
            if resp.status_code in [200, 201, 202, 204]:
                logger.info(f"[Sync] Sent delete request for inverter {inverter_id} (Server ID {inverter.server_id})")
                return True
            else:
                logger.warning(f"[Sync] Inverter delete request failed: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"[Sync] Inverter delete sync error: {e}")
            return False

    # =========================================================
    # BATTERY SYNC METHODS
    # =========================================================

    def initiate_battery_sync(self, battery_id: int) -> Optional[int]:
        """Gửi yêu cầu đồng bộ Battery (POST /api/batteries/requests/)"""
        battery = self.project_svc.get_battery_by_id(battery_id)
        if not battery or not battery.project_id: return None
        
        project_id = battery.project_id
        token, account_id = self._get_token_for_project(project_id)
        if not token: return None

        sync_info = self.project_svc.metadata_db.get_project_sync_info(project_id)
        if not sync_info: return None

        # Danh sách các trường Battery theo yêu cầu server
        batt_fields = {
            'battery_index', 'serial_number', 'brand', 'model',
            'capacity_kwh', 'capacity_ah', 'num_parallel_connections',
            'cells_per_module', 'modules_in_series', 'is_active',
            'replaced_by_id', 'usage_start_at', 'usage_end_at'
        }
        payload = {k: v for k, v in asdict(battery).items() if k in batt_fields}
        
        # Thêm các ID liên kết (Chỉ chọn 1 trong 2 theo yêu cầu server)
        server_id = sync_info.get("server_id")
        server_req_id = sync_info.get("server_request_id")
        
        if server_id:
            payload["project_id"] = server_id
        elif server_req_id:
            payload["project_request_id"] = server_req_id
        else:
            logger.warning(f"[Sync] Project {project_id} has neither server_id nor server_request_id. Battery sync will fail.")
            return -2
        
        if payload.get("usage_start_at") is None:
            payload["usage_start_at"] = datetime.now(timezone.utc).isoformat()

        try:
            base_api = API_BASE_URL.rstrip('/')
            url = f"{base_api}/api/batteries/requests/"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            # 0. Nếu battery ĐÃ ĐƯỢC DUYỆT hoặc BỊ TỪ CHỐI, ta gửi Request Update
            if battery.server_id and battery.sync_status in ['approved', 'rejected']:
                check_url = f"{base_api}/api/batteries/{battery.server_id}"
                get_resp = requests.get(check_url, headers=headers, timeout=10)
                if get_resp.status_code == 401:
                    token = self.auth.handle_unauthorized(account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        get_resp = requests.get(check_url, headers=headers, timeout=10)
                        
                if get_resp.status_code == 200:
                    server_data = get_resp.json()
                    has_changes = False
                    for k, v in payload.items():
                        if k in ["project_id", "project_request_id"]:
                            continue
                        if not self._is_equal(server_data.get(k), v):
                            has_changes = True
                            break
                            
                    if not has_changes:
                        logger.info(f"[Sync] Battery {battery_id} has no changes. Skipping update request.")
                        return -1
                
                update_payload = payload.copy()
                update_payload.pop("project_id", None)
                update_payload.pop("project_request_id", None)
                
                update_url = f"{base_api}/api/batteries/requests/update/{battery.server_id}"
                logger.info(f"[Sync] Sending Battery Update Request to {update_url}: {update_payload}")
                resp = requests.post(update_url, json=update_payload, headers=headers, timeout=20)
                
                if resp.status_code == 401:
                    token = self.auth.handle_unauthorized(account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        resp = requests.post(update_url, json=update_payload, headers=headers, timeout=20)
                
                if resp.status_code in [200, 201]:
                    new_req_id = resp.json().get("id")
                    if new_req_id:
                        self.project_svc.update_battery_sync(battery_id, server_request_id=new_req_id, status='pending')
                        logger.info(f"[Sync] Battery update request created: {new_req_id}")
                        return new_req_id
                
                logger.warning(f"[Sync] Battery Update Request failed: {resp.status_code} - {resp.text}")
                return None

            # 1. Nếu đang ở trạng thái pending
            if battery.server_request_id and battery.sync_status == 'pending':
                req_url = f"{base_api}/api/batteries/requests/{battery.server_request_id}"
                check_resp = requests.get(req_url, headers=headers, timeout=10)
                
                if check_resp.status_code == 401:
                    token = self.auth.handle_unauthorized(account_id)
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        check_resp = requests.get(req_url, headers=headers, timeout=10)
                        
                if check_resp.status_code == 200:
                    server_data = check_resp.json()
                    status = server_data.get("status", "").lower()
                    
                    if status == "pending":
                        logger.info(f"[Sync] Battery request {battery.server_request_id} is still pending.")
                        return -99
                    elif status == "approved":
                        server_id = server_data.get("approved_battery_id") or server_data.get("target_battery_id")
                        self.project_svc.update_battery_sync(battery_id, server_id=server_id, status='approved')
                        logger.info(f"[Sync] Battery request {battery.server_request_id} already approved.")
                        return self.initiate_battery_sync(battery_id)
                    elif status == "rejected":
                        logger.info(f"[Sync] Battery request {battery.server_request_id} was rejected. Allowing re-submission.")
                        self.project_svc.update_battery_sync(battery_id, server_request_id=0, status='rejected')
                        return self.initiate_battery_sync(battery_id)

            # 2. Tạo mới bằng POST nếu chưa có
            logger.info(f"[Sync] Sending Battery Create Request to {url}: {payload}")
            resp = requests.post(url, json=payload, headers=headers, timeout=20)
            
            if resp.status_code == 401:
                token = self.auth.handle_unauthorized(account_id)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = requests.post(url, json=payload, headers=headers, timeout=20)
                    
            if resp.status_code in [200, 201, 202]:
                res_data = resp.json()
                request_id = res_data.get("id")
                if request_id:
                    self.project_svc.update_battery_sync(battery_id, server_request_id=request_id, status='pending')
                    return request_id
            else:
                logger.warning(f"[Sync] Battery sync failed with status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"[Sync] Battery sync error: {e}")
        
        return None

    def background_poll_battery_status(self, request_id: int, battery_id: int):
        """Theo dõi trạng thái phê duyệt từ Admin cho Battery."""
        poll_key = f"batt_{request_id}"
        if poll_key in _ACTIVE_POLLS:
            return
            
        _ACTIVE_POLLS.add(poll_key)
        try:
            for _ in range(120):
                battery = self.project_svc.get_battery_by_id(battery_id)
                if not battery or not battery.project_id: break
                token, _ = self._get_token_for_project(battery.project_id)
                if not token:
                    time.sleep(60)
                    continue

                try:
                    url = f"{API_BASE_URL.rstrip('/')}/api/batteries/requests/{request_id}"
                    headers = {"Authorization": f"Bearer {token}"}
                    resp = requests.get(url, headers=headers, timeout=10)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status", "").lower()
                        
                        if status == "approved":
                            s_id = data.get("approved_battery_id") or data.get("target_battery_id")
                            self.project_svc.update_battery_sync(battery_id, server_id=s_id, status='approved')
                            logger.info(f"[Sync] Battery {battery_id} APPROVED by Admin.")
                            break
                        elif status == "rejected":
                            self.project_svc.update_battery_sync(battery_id, status='rejected')
                            break
                except Exception as e:
                    logger.error(f"[Sync] Polling battery error: {e}")
                
                time.sleep(60)
        finally:
            _ACTIVE_POLLS.discard(poll_key)

    def request_delete_battery_sync(self, battery_id: int) -> bool:
        """Gửi yêu cầu xoá Battery lên server (POST /api/batteries/requests/delete/{server_id})"""
        battery = self.project_svc.get_battery_by_id(battery_id)
        if not battery or not battery.server_id:
            return True

        token, account_id = self._get_token_for_project(battery.project_id)
        if not token: return False

        try:
            base_api = API_BASE_URL.rstrip('/')
            url = f"{base_api}/api/batteries/requests/delete/{battery.server_id}"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            resp = requests.post(url, headers=headers, timeout=20)
            if resp.status_code == 401:
                token = self.auth.handle_unauthorized(account_id)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = requests.post(url, headers=headers, timeout=20)
            
            if resp.status_code in [200, 201, 202, 204]:
                logger.info(f"[Sync] Sent delete request for battery {battery_id} (Server ID {battery.server_id})")
                return True
            else:
                logger.warning(f"[Sync] Battery delete request failed: {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"[Sync] Battery delete sync error: {e}")
            return False

    def cancel_sync(self, project_id: int) -> bool:
        """Hủy yêu cầu đồng bộ."""
        sync_info = self.project_svc.metadata_db.get_project_sync_info(project_id)
        if not sync_info or not sync_info.get("server_request_id"):
            return False

        request_id = sync_info["server_request_id"]
        token, _ = self._get_token_for_project(project_id)
        if not token: return False

        try:
            base_api = API_BASE_URL.rstrip('/')
            url = f"{base_api}/api/projects/requests/{request_id}"
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.delete(url, headers=headers, timeout=10)
            if resp.status_code in [200, 204]:
                self.project_svc.update_project_sync(project_id, status='pending', server_request_id=0)
                return True
        except Exception: pass
    def sync_project_to_server(self, project_id: int) -> Optional[int]:
        """
        [COMPATIBILITY WRAPPER] 
        Hàm này mô phỏng logic cũ nhưng sử dụng quy trình 'Advanced Sync'.
        Dùng cho các script hoặc UI cũ chưa cập nhật luồng từng bước.
        """
        logger.info(f"[Sync-Compat] Triggering sync for project {project_id}")
        
        # 1. Thử auto-match trước
        if self.pre_sync_check(project_id):
            proj = self.project_svc.get_project(project_id)
            return proj.server_id if proj else None
            
        # 2. Nếu không match, khởi tạo request mới
        request_id = self.initiate_sync_request(project_id)
        if request_id:
            logger.info(f"[Sync-Compat] Request {request_id} initiated. Starting background poll.")
            # Trong môi trường script, việc start thread polling có thể cần cân nhắc.
            # Nhưng để 'WEB chạy bình thường' (FastAPI), chúng ta có thể dùng BackgroundTasks 
            # Tuy nhiên ở layer Service này, chúng ta chỉ trả về ID và để API lo việc poll nếu cần.
            # Với script, user sẽ phải đợi hoặc chạy lại script sau.
            return None # Trả về None vì chưa có Server ID ngay lập tức
        
        return None

    def sync_inverters_to_server(self, project_id: int) -> int:
        """
        [COMPATIBILITY WRAPPER]
        Trả về số lượng inverter đang ở trạng thái chờ duyệt hoặc đã duyệt.
        """
        invs = self.project_svc.get_inverters_by_project(project_id)
        return len(invs)

    # ==============================
    # EVN & METER SETUP (WEB)
    # ==============================
    
    def get_evn_settings(self) -> dict:
        """Lấy cấu hình EVN toàn cục."""
        from backend.core import settings
        host = self.project_svc.metadata_db.get_setting("evn_modbus_host", settings.EVN_MODBUS_HOST)
        port = int(self.project_svc.metadata_db.get_setting("evn_modbus_port", settings.EVN_MODBUS_PORT))
        enabled = self.project_svc.metadata_db.get_setting("evn_enabled", str(settings.EVN_ENABLED)).lower() == "true"
        return {"host": host, "port": port, "enabled": enabled}

    def update_evn_settings(self, host: str, port: int, enabled: bool):
        """Lưu cấu hình EVN toàn cục."""
        self.project_svc.metadata_db.set_setting("evn_modbus_host", host)
        self.project_svc.metadata_db.set_setting("evn_modbus_port", port)
        self.project_svc.metadata_db.set_setting("evn_enabled", "true" if enabled else "false")

    def scan_meters(self, brand: str, model: str, comm_type: str, host: str, port: int, com_port: str, baudrate: int, slave_start: int, slave_end: int, polling_service) -> List[Dict]:
        """Thực hiện quét Meter qua polling service."""
        return polling_service.scan_meters(
            brand=brand, model=model, comm_type=comm_type,
            host=host, port=port, com_port=com_port, baudrate=baudrate,
            slave_start=slave_start, slave_end=slave_end
        )
