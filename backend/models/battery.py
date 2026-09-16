from dataclasses import dataclass
from typing import Optional
from datetime import datetime

# =========================
# CREATE
# =========================
@dataclass
class BatteryCreate:
    # ===== Identity =====
    serial_number: str
    brand: str
    model: str
    
    # ===== Battery Specifications =====
    capacity_kwh: Optional[float] = None
    capacity_ah: Optional[float] = None
    num_parallel_connections: Optional[int] = None
    cells_per_module: Optional[int] = None
    modules_in_series: Optional[int] = None
    
    # ===== Project / Structure =====
    battery_index: Optional[int] = None
    project_id: Optional[int] = None
    project_request_id: Optional[int] = None
    
    # ===== Logic & Status =====
    is_active: bool = True
    
    # ===== Lifecycle =====
    usage_start_at: Optional[str] = None
    usage_end_at: Optional[str] = None
    replaced_by_id: Optional[int] = None


# =========================
# UPDATE (PATCH)
# =========================
@dataclass
class BatteryUpdate:
    # ===== Identity =====
    serial_number: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    
    # ===== Battery Specifications =====
    capacity_kwh: Optional[float] = None
    capacity_ah: Optional[float] = None
    num_parallel_connections: Optional[int] = None
    cells_per_module: Optional[int] = None
    modules_in_series: Optional[int] = None
    
    # ===== Project / Structure =====
    battery_index: Optional[int] = None
    project_id: Optional[int] = None
    project_request_id: Optional[int] = None
    
    # ===== Logic & Status =====
    is_active: Optional[bool] = None
    
    # ===== Lifecycle =====
    usage_start_at: Optional[str] = None
    usage_end_at: Optional[str] = None
    replaced_by_id: Optional[int] = None


# =========================
# RESPONSE (READ)
# =========================
@dataclass
class BatteryResponse:
    # ===== Primary =====
    id: int
    project_id: Optional[int]
    
    # ===== Identity =====
    serial_number: str
    brand: str
    model: str
    
    # ===== Battery Specifications =====
    capacity_kwh: Optional[float] = None
    capacity_ah: Optional[float] = None
    num_parallel_connections: Optional[int] = None
    cells_per_module: Optional[int] = None
    modules_in_series: Optional[int] = None
    
    # ===== Project / Structure =====
    battery_index: Optional[int] = None
    project_request_id: Optional[int] = None
    
    # ===== Logic & Status =====
    is_active: Optional[bool] = True
    
    # ===== Lifecycle =====
    usage_start_at: Optional[str] = None
    usage_end_at: Optional[str] = None
    replaced_by_id: Optional[int] = None
    
    # ===== System / Sync =====
    server_id: Optional[int] = None
    server_request_id: Optional[int] = None
    sync_status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
