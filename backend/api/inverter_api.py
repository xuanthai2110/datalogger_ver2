"""
web/routes/inverter_route.py — CRUD routes cho Inverters
"""

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from backend.services.project_service import ProjectService
from backend.models.inverter import InverterCreate, InverterUpdate
from dataclasses import asdict, fields
import logging
from backend.core import settings as app_config

router = APIRouter(tags=["inverters"])
logger = logging.getLogger(__name__)

def get_project_service() -> ProjectService:
    from backend.db_manager import MetadataDB, RealtimeDB
    return ProjectService(MetadataDB(app_config.METADATA_DB), RealtimeDB(app_config.REALTIME_DB))


def _format_inverter_response(inv) -> dict:
    if inv is None:
        return None
    data = asdict(inv)
    is_act = bool(inv.is_active)
    data["is_active"] = is_act
    data["status"] = "Hoạt động" if is_act else "Ngưng hoạt động"
    data["status_text"] = "Hoạt động" if is_act else "Ngưng hoạt động"
    data["operating_status"] = "Hoạt động" if is_act else "Ngưng hoạt động"
    data["state"] = "ACTIVE" if is_act else "INACTIVE"
    return data


def _normalize_inverter_body(body: dict) -> dict:
    """Chuẩn hóa dữ liệu body truyền vào API (xử lý status, is_active, datetime string)."""
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
def list_inverters(svc: ProjectService = Depends(get_project_service)):
    """Trả về tất cả thông tin của tất cả inverter."""
    try:
        inverters = svc.get_all_inverters()
        return [_format_inverter_response(i) for i in inverters]
    except Exception as e:
        logger.error(f"list_inverters error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.get("/{inverter_id}")
def get_inverter_id(inverter_id: int, svc: ProjectService = Depends(get_project_service)):
    """Trả về thông tin của inverter có id tương ứng."""
    try:
        inv = svc.get_inverter_by_id(inverter_id)
        if not inv:
            return JSONResponse(status_code=404, content={"detail": [{"loc": ["path", "inverter_id"], "msg": "Inverter not found", "type": "not_found"}]})
        return _format_inverter_response(inv)
    except Exception as e:
        logger.error(f"get_inverter error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.post("")
def create_inverter(
    svc: ProjectService = Depends(get_project_service),
    body: dict = Body(..., example={
    "project_id": 1,
    "brand": "Huawei",
    "model": "SUN2000-110KTL",
    "serial_number": "HV1234567890",
    "capacity_kw": 110.0,
    "mppt_count": 10,
    "phase_count": 3,
    "string_count": 20,
    "rate_dc_kwp": 120.0,
    "rate_ac_kw": 110.0,
    "is_active": True,
    "slave_id": 1
})):
    """Tạo inverter mới trong local DB qua Service."""
    try:
        norm_body = _normalize_inverter_body(body)
        valid_fields = {f.name for f in fields(InverterCreate)}
        filtered_body = {k: v for k, v in norm_body.items() if k in valid_fields and k != "id"}
        
        inv_id = svc.upsert_inverter(InverterCreate(**filtered_body))
        inv = svc.get_inverter_by_id(inv_id)
        return _format_inverter_response(inv)
    except Exception as e:
        logger.error(f"create_inverter error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.patch("/{inverter_id}")
def update_inverter(
    inverter_id: int,
    svc: ProjectService = Depends(get_project_service),
    body: dict = Body(..., example={
    "capacity_kw": 115.0,
    "is_active": False
})):
    """Cập nhật thông tin của inverter có id tương ứng qua Service."""
    try:
        logger.info(f"[InverterAPI] PATCH /api/inverters/{inverter_id} - Raw body: {body}")
        norm_body = _normalize_inverter_body(body)
        logger.info(f"[InverterAPI] Normalized body: {norm_body}")
        
        valid_fields = {f.name for f in fields(InverterUpdate)}
        filtered_body = {k: v for k, v in norm_body.items() if k in valid_fields and k != "id"}
        logger.info(f"[InverterAPI] Filtered body for InverterUpdate: {filtered_body}")
        
        svc.patch_inverter(inverter_id, InverterUpdate(**filtered_body))
        try:
            svc.metadata_db.set_setting("polling_config_changed", "true")
            logger.info("[InverterAPI] Triggered polling_config_changed flag in DB.")
        except Exception as err:
            logger.warning(f"[InverterAPI] Could not set polling_config_changed flag: {err}")

        inv = svc.get_inverter_by_id(inverter_id)
        if not inv:
            logger.warning(f"[InverterAPI] Inverter ID {inverter_id} not found after patch")
            return JSONResponse(status_code=404, content={"ok": False, "error": "Inverter not found"})
        
        resp = _format_inverter_response(inv)
        logger.info(f"[InverterAPI] Update successful for ID {inverter_id} -> DB state: is_active={resp.get('is_active')}, status='{resp.get('status')}'")
        return resp
    except Exception as e:
        logger.error(f"[InverterAPI] update_inverter error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.delete("/{inverter_id}")
def delete_inverter(inverter_id: int, svc: ProjectService = Depends(get_project_service)):
    """Xoá inverter có id tương ứng qua Service."""
    try:
        from backend.api.sync_api import get_setup_service
        setup_svc = get_setup_service()
        setup_svc.request_delete_inverter_sync(inverter_id)
        
        svc.delete_inverter(inverter_id)
        return {"message": "Inverter deleted successfully"}
    except Exception as e:
        logger.error(f"delete_inverter error: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

