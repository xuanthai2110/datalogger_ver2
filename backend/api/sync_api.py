from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from backend.services.setup_service import SetupService
from backend.core import settings as app_config

def get_setup_service() -> SetupService:
    from backend.db_manager import MetadataDB, RealtimeDB
    from backend.services.project_service import ProjectService
    from backend.services.auth_service import AuthService
    
    metadata_db = MetadataDB(app_config.METADATA_DB)
    realtime_db = RealtimeDB(app_config.REALTIME_DB)
    project_svc = ProjectService(metadata_db, realtime_db)
    auth_svc = AuthService(metadata_db)
    return SetupService(auth_svc, project_svc)

router = APIRouter(prefix="/api/sync", tags=["sync"])

@router.post("/project/{project_id}")
async def sync_project(
    project_id: int, 
    background_tasks: BackgroundTasks, 
    svc: SetupService = Depends(get_setup_service)
):
    # 1. Kiểm tra xem đã có trên server chưa (Pre-sync check)
    if svc.pre_sync_check(project_id):
        return {"ok": True, "message": "Project matched and approved automatically from server."}
    

    request_id = svc.initiate_project_sync(project_id)
    if request_id == -1:
        return {"ok": True, "message": "Project is already up-to-date with the server. No changes detected."}
    if not request_id:
        raise HTTPException(status_code=502, detail="Cloud server rejected the project request or is unreachable.")
    
    # Kiểm tra lại trạng thái sau khi sync (có thể đã được auto-approved do trùng khớp SN/Meter)
    fresh_project = svc.project_svc.get_project(project_id)
    if fresh_project and fresh_project.sync_status == 'approved':
        return {
            "ok": True,
            "server_id": fresh_project.server_id,
            "message": "Dự án đã được tự động khớp và phê duyệt trên Server (Auto-matched)."
        }

    # 3. Chạy polling trong background để theo dõi kết quả phê duyệt
    background_tasks.add_task(svc.background_poll_status, request_id, project_id)
    
    return {
        "ok": True, 
        "server_request_id": request_id, 
        "message": "Yêu cầu đồng bộ đã gửi. Vui lòng liên hệ Admin (0836684169) để được duyệt nhanh."
    }

@router.post("/inverter/{inverter_id}")
async def sync_inverter(
    inverter_id: int, 
    background_tasks: BackgroundTasks,
    svc: SetupService = Depends(get_setup_service)
):

    request_id = svc.initiate_inverter_sync(inverter_id)
    
    if request_id == -99:
        return {"ok": False, "message": "Yêu cầu trước đó vẫn đang chờ phê duyệt. Vui lòng gọi đến 0836684169 để xử lý!"}
    
    if request_id == -2:
        return {"ok": False, "message": "Vui lòng tạo yêu cầu đồng bộ cho Dự án (Project) trước khi đồng bộ Inverter!"}
    
    if request_id == -3:
        return {"ok": True, "message": "Inverter đã được cập nhật thành công trực tiếp lên Server."}
    
    if request_id == -1:
        return {"ok": True, "message": "Dữ liệu Inverter local đã khớp hoàn toàn với Server. Không cần cập nhật."}
    
    if not request_id:
        raise HTTPException(status_code=502, detail="Cloud server rejected the inverter request.")
    
    # 3. Chạy polling trong background để theo dõi kết quả phê duyệt cho inverter
    background_tasks.add_task(svc.background_poll_inverter_status, request_id, inverter_id)
    
    return {
        "ok": True, 
        "server_request_id": request_id, 
        "message": "Inverter sync request sent."
    }

@router.delete("/project/{project_id}/stop")
async def stop_sync(
    project_id: int, 
    svc: SetupService = Depends(get_setup_service)
):
    success = svc.cancel_sync(project_id)
    if not success:
        raise HTTPException(status_code=400, detail="Could not cancel sync (maybe no pending request exists).")
    return {"ok": True, "message": "Sync request cancelled and local status reset."}

@router.post("/project/{project_id}/delete")
async def sync_delete_project(
    project_id: int, 
    svc: SetupService = Depends(get_setup_service)
):

    success = svc.request_delete_project_sync(project_id)
    if not success:
        raise HTTPException(status_code=502, detail="Cloud server rejected the delete request.")
    
    return {"ok": True, "message": "Project delete request sent successfully."}

@router.post("/inverter/{inverter_id}/delete")
async def sync_delete_inverter(
    inverter_id: int, 
    svc: SetupService = Depends(get_setup_service)
):

    success = svc.request_delete_inverter_sync(inverter_id)
    if not success:
        raise HTTPException(status_code=502, detail="Cloud server rejected the delete request.")
    
    return {"ok": True, "message": "Inverter delete request sent successfully."}

@router.post("/battery/{battery_id}")
async def sync_battery(
    battery_id: int, 
    background_tasks: BackgroundTasks,
    svc: SetupService = Depends(get_setup_service)
):

    request_id = svc.initiate_battery_sync(battery_id)
    
    if request_id == -99:
        return {"ok": False, "message": "Yêu cầu trước đó vẫn đang chờ phê duyệt. Vui lòng gọi đến 0836684169 để xử lý!"}
    
    if request_id == -2:
        return {"ok": False, "message": "Vui lòng tạo yêu cầu đồng bộ cho Dự án (Project) trước khi đồng bộ Battery!"}
    
    if request_id == -1:
        return {"ok": True, "message": "Dữ liệu Battery local đã khớp hoàn toàn với Server. Không cần cập nhật."}
    
    if not request_id:
        raise HTTPException(status_code=502, detail="Cloud server rejected the battery request.")
    
    background_tasks.add_task(svc.background_poll_battery_status, request_id, battery_id)
    
    return {
        "ok": True, 
        "server_request_id": request_id, 
        "message": "Battery sync request sent."
    }

@router.post("/battery/{battery_id}/delete")
async def sync_delete_battery(
    battery_id: int, 
    svc: SetupService = Depends(get_setup_service)
):

    success = svc.request_delete_battery_sync(battery_id)
    if not success:
        raise HTTPException(status_code=502, detail="Cloud server rejected the delete request.")
    
    return {"ok": True, "message": "Battery delete request sent successfully."}
