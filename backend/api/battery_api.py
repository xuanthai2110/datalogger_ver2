"""
backend/api/battery_api.py — CRUD routes cho Batteries
"""

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from backend.services.project_service import ProjectService
from backend.models.battery import BatteryCreate, BatteryUpdate
from dataclasses import asdict, fields
import logging
from backend.core import settings as app_config

router = APIRouter(tags=["batteries"])
logger = logging.getLogger(__name__)

def get_project_service() -> ProjectService:
    from backend.db_manager import MetadataDB, RealtimeDB
    return ProjectService(MetadataDB(app_config.METADATA_DB), RealtimeDB(app_config.REALTIME_DB))


def _format_battery_response(batt) -> dict:
    if batt is None:
        return None
    data = asdict(batt)
    is_act = bool(batt.is_active)
    data["is_active"] = is_act
    data["status"] = "Hoạt động" if is_act else "Ngưng hoạt động"
    data["status_text"] = "Hoạt động" if is_act else "Ngưng hoạt động"
    data["operating_status"] = "Hoạt động" if is_act else "Ngưng hoạt động"
    data["state"] = "ACTIVE" if is_act else "INACTIVE"
    return data


def _normalize_battery_body(body: dict) -> dict:
    """Chuẩn hóa dữ liệu body truyền vào API."""
    normalized = body.copy()

    # 1. Ánh xạ các tên trường trạng thái
    status_val = None
    for k in ("is_active", "status", "state", "trang_thai"):
        if k in normalized and normalized[k] is not None:
            status_val = normalized[k]
            break

    if status_val is not None:
        if isinstance(status_val, bool):
            normalized["is_active"] = status_val
        elif isinstance(status_val, (int, float)):
            normalized["is_active"] = (status_val != 0)
        elif isinstance(status_val, str):
            s_lower = status_val.strip().lower()
            if s_lower in ("false", "0", "off", "disabled", "inactive", "ngưng hoạt động", "ngung hoat dong", "ngừng hoạt động", "tắt", "tat", "stopped"):
                normalized["is_active"] = False
            elif s_lower in ("true", "1", "on", "enabled", "active", "đang hoạt động", "dang hoat dong", "bật", "bat", "running"):
                normalized["is_active"] = True
            else:
                normalized["is_active"] = bool(status_val)

    # 2. Chuẩn hóa datetime & foreign keys
    for field in ("usage_start_at", "usage_end_at"):
        if field in normalized and (normalized[field] == "" or normalized[field] == 0):
            normalized[field] = None

    if "replaced_by_id" in normalized:
        val = normalized["replaced_by_id"]
        if val == "" or val == 0 or val is None:
            normalized["replaced_by_id"] = None
        else:
            try:
                normalized["replaced_by_id"] = int(val)
            except (ValueError, TypeError):
                normalized["replaced_by_id"] = None

    return normalized


@router.get("")
def list_batteries(svc: ProjectService = Depends(get_project_service)):
    """Trả về tất cả thông tin của tất cả battery."""
    try:
        batteries = svc.get_all_batteries()
        return [_format_battery_response(b) for b in batteries]
    except Exception as e:
        logger.error(f"list_batteries error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.get("/{battery_id}")
def get_battery_id(battery_id: int, svc: ProjectService = Depends(get_project_service)):
    """Trả về thông tin của battery có id tương ứng."""
    try:
        batt = svc.get_battery_by_id(battery_id)
        if not batt:
            return JSONResponse(status_code=404, content={"detail": [{"loc": ["path", "battery_id"], "msg": "Battery not found", "type": "not_found"}]})
        return _format_battery_response(batt)
    except Exception as e:
        logger.error(f"get_battery error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.post("")
def create_battery(
    svc: ProjectService = Depends(get_project_service),
    body: dict = Body(..., example={
    "project_id": 1,
    "brand": "BYD",
    "model": "Premium HVS",
    "serial_number": "BATT_1234567890",
    "capacity_kwh": 10.2,
    "capacity_ah": 100.0,
    "num_parallel_connections": 1,
    "cells_per_module": 16,
    "modules_in_series": 4,
    "is_active": True
})):
    """Tạo battery mới trong local DB qua Service."""
    try:
        norm_body = _normalize_battery_body(body)
        valid_fields = {f.name for f in fields(BatteryCreate)}
        filtered_body = {k: v for k, v in norm_body.items() if k in valid_fields and k != "id"}
        
        batt_res = svc.upsert_battery(BatteryCreate(**filtered_body))
        batt = svc.get_battery_by_id(batt_res.id)
        return _format_battery_response(batt)
    except Exception as e:
        logger.error(f"create_battery error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.patch("/{battery_id}")
def update_battery(
    battery_id: int,
    svc: ProjectService = Depends(get_project_service),
    body: dict = Body(..., example={
    "capacity_kwh": 12.5,
    "is_active": False
})):
    """Cập nhật thông tin của battery có id tương ứng qua Service."""
    try:
        logger.info(f"[BatteryAPI] PATCH /api/batteries/{battery_id} - Raw body: {body}")
        norm_body = _normalize_battery_body(body)
        
        valid_fields = {f.name for f in fields(BatteryUpdate)}
        filtered_body = {k: v for k, v in norm_body.items() if k in valid_fields and k != "id"}
        
        svc.patch_battery(battery_id, BatteryUpdate(**filtered_body))
        
        batt = svc.get_battery_by_id(battery_id)
        if not batt:
            return JSONResponse(status_code=404, content={"ok": False, "error": "Battery not found"})
        
        resp = _format_battery_response(batt)
        return resp
    except Exception as e:
        logger.error(f"[BatteryAPI] update_battery error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.delete("/{battery_id}")
def delete_battery(battery_id: int, svc: ProjectService = Depends(get_project_service)):
    """Xoá battery có id tương ứng qua Service."""
    try:
        from backend.api.sync_api import get_setup_service
        setup_svc = get_setup_service()
        setup_svc.request_delete_battery_sync(battery_id)
        
        svc.delete_battery(battery_id)
        return {"message": "Battery deleted successfully"}
    except Exception as e:
        logger.error(f"delete_battery error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
