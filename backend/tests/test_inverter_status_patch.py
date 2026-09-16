import pytest
import os
import tempfile
from backend.db_manager import MetadataDB, RealtimeDB
from backend.services.project_service import ProjectService
from backend.models.project import ProjectCreate
from backend.models.inverter import InverterCreate, InverterUpdate
from backend.api import inverter_api
from backend.api.inverter_api import _normalize_inverter_body, update_inverter, get_inverter_id, list_inverters

def test_normalize_inverter_body():
    # Test status string "Ngưng hoạt động" -> is_active = False
    norm1 = _normalize_inverter_body({"status": "Ngưng hoạt động"})
    assert norm1.get("is_active") is False
    
    # Test is_active string "false" -> is_active = False
    norm2 = _normalize_inverter_body({"is_active": "false"})
    assert norm2.get("is_active") is False
    
    # Test status string "INACTIVE" -> is_active = False
    norm3 = _normalize_inverter_body({"status": "INACTIVE"})
    assert norm3.get("is_active") is False

    # Test status string "Đang hoạt động" -> is_active = True
    norm4 = _normalize_inverter_body({"status": "Đang hoạt động"})
    assert norm4.get("is_active") is True

    # Test datetime empty string -> None
    norm5 = _normalize_inverter_body({"usage_start_at": ""})
    assert norm5.get("usage_start_at") is None


def test_inverter_patch_status_db_integration(tmp_path):
    db_path = str(tmp_path / "test_meta.db")
    rt_path = str(tmp_path / "test_rt.db")
    meta_db = MetadataDB(db_path)
    rt_db = RealtimeDB(rt_path)
    svc = ProjectService(meta_db, rt_db)

    # 1. Create a dummy project & inverter
    p_id = meta_db.post_project(ProjectCreate(
        name='Test Plant', elec_meter_no='TEST1234', elec_price_per_kwh=1783.0,
        location='Hanoi', lat=21.0, lon=105.0,
        capacity_kwp=100.0, ac_capacity_kw=100.0, inverter_count=1
    ))

    inv_resp = meta_db.upsert_inverter(InverterCreate(
        project_id=p_id, brand="Sungrow", model="SG110CX",
        serial_number="TEST_INV_SN_001", capacity_kw=110.0, is_active=True, slave_id=1
    ))
    inv_id = inv_resp.id

    # Verify initial status is active (1 / True)
    inv = meta_db.get_inverter_by_id(inv_id)
    assert inv.is_active is True

    # Test 1: PATCH with {"status": "Ngưng hoạt động"}
    res1 = update_inverter(inverter_id=inv_id, svc=svc, body={"status": "Ngưng hoạt động"})
    assert res1["is_active"] is False
    assert res1["status"] == "Ngưng hoạt động"

    # Direct DB Check
    db_inv1 = meta_db.get_inverter_by_id(inv_id)
    assert db_inv1.is_active is False

    # Test 2: PATCH với trạng thái Hoạt động
    res2 = update_inverter(inverter_id=inv_id, svc=svc, body={"status": "Hoạt động"})
    assert res2["is_active"] is True
    assert res2["status"] in ("Hoạt động", "Đang hoạt động")

    # Direct DB Check
    db_inv2 = meta_db.get_inverter_by_id(inv_id)
    assert db_inv2.is_active is True

    # Test 3: PATCH with {"is_active": "false"} (string)
    res3 = update_inverter(inverter_id=inv_id, svc=svc, body={"is_active": "false"})
    assert res3["is_active"] is False
    assert res3["status"] == "Ngưng hoạt động"

    # Direct DB Check
    db_inv3 = meta_db.get_inverter_by_id(inv_id)
    assert db_inv3.is_active is False

    # Test 4: GET Inverter response contains status alias
    get_res = get_inverter_id(inverter_id=inv_id, svc=svc)
    assert get_res["is_active"] is False
    assert get_res["status"] == "Ngưng hoạt động"
