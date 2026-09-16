import logging
from dataclasses import asdict
from typing import Optional, List, Dict, Any
from backend.models.project import ProjectCreate, ProjectResponse, ProjectUpdate
from backend.models.inverter import InverterCreate, InverterResponse, InverterUpdate
from backend.models.battery import BatteryCreate, BatteryResponse, BatteryUpdate
from backend.models.realtime import ProjectRealtimeResponse, ProjectRealtimeCreate
from backend.models.meter import MeterCreate, MeterResponse, MeterUpdate
import requests
import time
import threading
from backend.core.settings import API_BASE_URL

logger = logging.getLogger(__name__)

class ProjectService:
    def __init__(self, metadata_db, realtime_db, cache_db=None):
        self.metadata_db = metadata_db
        self.realtime_db = realtime_db
        self.cache_db = cache_db

    # ==============================
    # PROJECT
    # ==============================

    def create_project(self, data: ProjectCreate) -> int:
        return self.metadata_db.post_project(data)
    
    def get_project(self, project_id: int) -> Optional[ProjectResponse]:
        return self.metadata_db.get_project(project_id)

    def get_projects(self) -> List[ProjectResponse]:
        return self.metadata_db.get_projects()

    def update_project(self, project_id: int, data: ProjectUpdate):
        return self.metadata_db.patch_project(project_id, data)

    def update_project_sync(self, project_id: int, server_id: Optional[int] = None, server_request_id: Optional[int] = None, status: str = 'pending'):
        return self.metadata_db.update_project_sync(project_id, server_id, server_request_id, status)

    def upsert_project(self, data: ProjectCreate, project_id: Optional[int] = None) -> ProjectResponse:
        return self.metadata_db.upsert_project(data, project_id)

    def delete_project(self, project_id):
        """Xoá project và toàn bộ dữ liệu liên quan"""
        inverters = self.metadata_db.get_inverters_by_project(project_id)
        for inv in inverters:
            self.realtime_db.delete_inverter_data(inv.id)
        
        self.realtime_db.delete_project_data(project_id)
        self.metadata_db.delete_project(project_id)
        return True

    # ==============================
    # INVERTER
    # ==============================

    def get_all_inverters(self) -> List[InverterResponse]:
        return self.metadata_db.get_all_inverters()

    def create_inverter(self, data: InverterCreate) -> int:
        return self.metadata_db.post_inverter(data)

    def upsert_inverter(self, data: InverterCreate) -> int:
        return self.metadata_db.upsert_inverter(data)

    def patch_inverter(self, inverter_id: int, updates: InverterUpdate):
        return self.metadata_db.patch_inverter(inverter_id, updates)

    def get_inverter_by_id(self, inverter_id: int) -> Optional[InverterResponse]:
        return self.metadata_db.get_inverter_by_id(inverter_id)

    def delete_inverter(self, inverter_id: int):
        self.realtime_db.delete_inverter_data(inverter_id)
        self.metadata_db.delete_inverter(inverter_id)
        return True

    def get_inverters_by_project(self, project_id: int) -> List[InverterResponse]:
        return self.metadata_db.get_inverters_by_project(project_id)

    def update_inverter_sync(self, inverter_id: int, server_id: Optional[int] = None, server_request_id: Optional[int] = None, status: str = 'pending'):
        return self.metadata_db.update_inverter_sync(inverter_id, server_id, server_request_id, status)

    # ==============================
    # CACHE (RAM) - Dành cho Polling & Realtime UI
    # ==============================

    def upsert_inverter_ac_cache(self, inverter_id: int, project_id: int, data: dict):
        if self.cache_db:
            self.cache_db.upsert_inverter_ac(inverter_id, project_id, data)

    def upsert_mppt_cache(self, inverter_id: int, project_id: int, mppts: List[dict]):
        if self.cache_db:
            self.cache_db.upsert_mppt_batch(inverter_id, project_id, mppts)

    def upsert_string_cache(self, inverter_id: int, project_id: int, strings: List[dict]):
        if self.cache_db:
            self.cache_db.upsert_string_batch(inverter_id, project_id, strings)

    def upsert_error_cache(self, inverter_id: int, project_id: int, status_code: int, fault_code: int):
        if self.cache_db:
            self.cache_db.upsert_error(inverter_id, project_id, status_code, fault_code)

    # ==============================
    # OUTBOX - Dành cho Telemetry & Uploader
    # ==============================

    def post_to_outbox(self, project_id: int, server_id: int, data: dict, data_type: str = "Project"):
        self.realtime_db.post_to_outbox(project_id, server_id, data, data_type=data_type)

    def get_all_outbox(self) -> List[dict]:
        return self.realtime_db.get_all_outbox()

    def delete_from_outbox(self, record_id: int):
        self.realtime_db.delete_from_outbox(record_id)

    # ==============================
    # REALTIME (DISK) - Lưu trữ lịch sử
    # ==============================

    def get_latest_project_data(self, project_id: int):
        return self.realtime_db.get_latest_project_realtime(project_id)

    def cleanup_old_data(self, before_timestamp: str):
        return self.realtime_db.delete_before(before_timestamp)

    def get_project_sync_info(self, project_id: int):
        return self.metadata_db.get_project_sync_info(project_id)

    # ==============================
    # METER
    # ==============================
    def get_meters_by_project(self, project_id: int) -> List[MeterResponse]:
        return self.metadata_db.get_meters_by_project(project_id)

    def create_meter(self, data: MeterCreate) -> int:
        return self.metadata_db.post_meter(data)

    def update_meter(self, meter_id: int, data: MeterUpdate):
        return self.metadata_db.patch_meter(meter_id, data)

    def delete_meter(self, meter_id: int):
        return self.metadata_db.delete_meter(meter_id)

    # ==============================
    # BATTERY
    # ==============================
    def get_all_batteries(self) -> List[BatteryResponse]:
        return self.metadata_db.get_all_batteries()

    def create_battery(self, data: BatteryCreate) -> int:
        return self.metadata_db.post_battery(data)

    def upsert_battery(self, data: BatteryCreate) -> BatteryResponse:
        return self.metadata_db.upsert_battery(data)

    def patch_battery(self, battery_id: int, updates: BatteryUpdate):
        return self.metadata_db.patch_battery(battery_id, updates)

    def get_battery_by_id(self, battery_id: int) -> Optional[BatteryResponse]:
        return self.metadata_db.get_battery_by_id(battery_id)

    def get_battery_by_serial(self, serial: str) -> Optional[BatteryResponse]:
        return self.metadata_db.get_battery_by_serial(serial)

    def delete_battery(self, battery_id: int):
        return self.metadata_db.delete_battery(battery_id)

    def get_batteries_by_project(self, project_id: int) -> List[BatteryResponse]:
        return self.metadata_db.get_batteries_by_project(project_id)

    def update_battery_sync(self, battery_id: int, server_id: Optional[int] = None, server_request_id: Optional[int] = None, status: str = 'pending'):
        return self.metadata_db.update_battery_sync(battery_id, server_id, server_request_id, status)

