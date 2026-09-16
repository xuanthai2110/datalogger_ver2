from dataclasses import dataclass
from typing import Optional

# =========================
# PROJECT REALTIME
# =========================
@dataclass
class ProjectRealtimeCreate:
    project_id: int
    Temp_C: float = 0
    P_ac: float = 0
    P_dc: float = 0
    E_daily: float = 0
    E_monthly: float = 0
    delta_E_monthly: float = 0
    E_total: float = 0
    severity: str = "STABLE"
    created_at: str = ""


@dataclass
class ProjectRealtimeResponse:
    id: int
    project_id: int
    Temp_C: float = 0
    P_ac: float = 0
    P_dc: float = 0
    E_daily: float = 0
    E_monthly: float = 0
    delta_E_monthly: float = 0
    E_total: float = 0
    severity: str = "STABLE"
    created_at: str = ""

# =========================
# INVERTER AC REALTIME
# =========================
@dataclass
class InverterACRealtimeCreate:
    project_id: int
    inverter_id: int
    IR: float
    Temp_C: float
    P_ac: float
    Q_ac: float
    V_a: float
    V_b: float
    V_c: float
    I_a: float
    I_b: float
    I_c: float
    PF: float
    H: float
    E_daily: float
    delta_E_monthly: float
    E_monthly: float
    E_total: float
    created_at: Optional[str] = None

@dataclass
class InverterACRealtimeResponse:
    id: int
    project_id: int
    inverter_id: int
    IR: float
    Temp_C: float
    P_ac: float
    Q_ac: float
    V_a: float
    V_b: float
    V_c: float
    I_a: float
    I_b: float
    I_c: float
    PF: float
    H: float
    E_daily: float
    delta_E_monthly: float
    E_monthly: float
    E_total: float
    created_at: Optional[str] = None    

# =========================
# INVERTER ERRORS
# =========================
@dataclass
class InverterErrorCreate:
    project_id: int
    inverter_id: int
    fault_code: int
    fault_description: str
    repair_instruction: str
    severity: str
    created_at: Optional[str] = None

@dataclass
class InverterErrorResponse:
    id: int
    project_id: int
    inverter_id: int
    fault_code: int
    fault_description: str
    repair_instruction: str
    severity: str
    created_at: Optional[str] = None
@dataclass
class mpptRealtimeCreate:
    project_id: int
    inverter_id: int
    mppt_index: int
    string_on_mppt: int = 0
    V_mppt: float = 0
    I_mppt: float = 0
    P_mppt: float = 0
    Max_I: float = 0
    Max_P: float = 0
    Max_V: float = 0
    created_at: Optional[str] = None

@dataclass
class mpptRealtimeResponse:
    id: int
    project_id: int
    inverter_id: int
    mppt_index: int
    string_on_mppt: int = 0
    V_mppt: float = 0
    I_mppt: float = 0
    P_mppt: float = 0
    Max_I: float = 0
    Max_P: float = 0
    Max_V: float = 0
    created_at: Optional[str] = None
@dataclass
class stringRealtimeCreate:
    project_id: int
    inverter_id: int
    mppt_id: int
    string_id: int
    I_string: float = 0
    max_I: float = 0
    created_at: Optional[str] = None

@dataclass
class stringRealtimeResponse:
    id: int
    project_id: int
    inverter_id: int
    mppt_id: int
    string_id: int
    I_string: float = 0
    max_I: float = 0
    created_at: Optional[str] = None


# =========================
# BATTERY REALTIME
# =========================
@dataclass
class BatteryRealtimeCreate:
    project_id: int
    inverter_id: Optional[int] = None
    battery_id: Optional[int] = None
    serial_number: str = ""
    inv_batt_u: float = 0.0
    inv_batt_i: float = 0.0
    inv_batt_p: float = 0.0
    bms_batt_u: float = 0.0
    bms_batt_i: float = 0.0
    bms_batt_p: float = 0.0
    bms_batt_soc: float = 0.0
    bms_batt_soh: float = 0.0
    batt_direction: int = -1
    e_charge_daily: float = 0.0
    e_discharge_daily: float = 0.0
    e_charge_total: float = 0.0
    e_discharge_total: float = 0.0
    bms_min_cell_temp: float = 0.0
    bms_max_cell_temp: float = 0.0
    bms_min_cell_volt: float = 0.0
    bms_max_cell_volt: float = 0.0
    created_at: Optional[str] = None


@dataclass
class BatteryRealtimeResponse:
    id: int
    project_id: int
    inverter_id: Optional[int] = None
    battery_id: Optional[int] = None
    serial_number: str = ""
    inv_batt_u: float = 0.0
    inv_batt_i: float = 0.0
    inv_batt_p: float = 0.0
    bms_batt_u: float = 0.0
    bms_batt_i: float = 0.0
    bms_batt_p: float = 0.0
    bms_batt_soc: float = 0.0
    bms_batt_soh: float = 0.0
    batt_direction: int = -1
    e_charge_daily: float = 0.0
    e_discharge_daily: float = 0.0
    e_charge_total: float = 0.0
    e_discharge_total: float = 0.0
    bms_min_cell_temp: float = 0.0
    bms_max_cell_temp: float = 0.0
    bms_min_cell_volt: float = 0.0
    bms_max_cell_volt: float = 0.0
    created_at: Optional[str] = None


# =========================
# LOAD REALTIME
# =========================
@dataclass
class LoadRealtimeCreate:
    project_id: int
    inverter_id: Optional[int] = None
    p_load: float = 0.0
    s_backup_load: float = 0.0
    u_backup_a: float = 0.0
    u_backup_b: float = 0.0
    u_backup_c: float = 0.0
    i_backup_a: float = 0.0
    i_backup_b: float = 0.0
    i_backup_c: float = 0.0
    p_backup_a: float = 0.0
    p_backup_b: float = 0.0
    p_backup_c: float = 0.0
    e_daily: float = 0.0
    e_total: float = 0.0
    e_backup_daily: float = 0.0
    e_backup_total: float = 0.0
    created_at: Optional[str] = None


@dataclass
class LoadRealtimeResponse:
    id: int
    project_id: int
    inverter_id: Optional[int] = None
    p_load: float = 0.0
    s_backup_load: float = 0.0
    u_backup_a: float = 0.0
    u_backup_b: float = 0.0
    u_backup_c: float = 0.0
    i_backup_a: float = 0.0
    i_backup_b: float = 0.0
    i_backup_c: float = 0.0
    p_backup_a: float = 0.0
    p_backup_b: float = 0.0
    p_backup_c: float = 0.0
    e_daily: float = 0.0
    e_total: float = 0.0
    e_backup_daily: float = 0.0
    e_backup_total: float = 0.0
    created_at: Optional[str] = None


# =========================
# METER (GRID) REALTIME
# =========================
@dataclass
class MeterRealtimeCreate:
    project_id: int
    meter_id: Optional[int] = None
    serial_number: str = ""
    u_a: float = 0.0
    u_b: float = 0.0
    u_c: float = 0.0
    i_a: float = 0.0
    i_b: float = 0.0
    i_c: float = 0.0
    p_a: float = 0.0
    p_b: float = 0.0
    p_c: float = 0.0
    P_total: float = 0.0
    Q_total: float = 0.0
    S_total: float = 0.0
    PF: float = 0.0
    f: float = 0.0
    imp_pt_today: float = 0.0
    exp_pt_today: float = 0.0
    imp_pt_total: float = 0.0
    exp_pt_total: float = 0.0
    created_at: Optional[str] = None


@dataclass
class MeterRealtimeResponse:
    id: int
    project_id: int
    meter_id: Optional[int] = None
    serial_number: str = ""
    u_a: float = 0.0
    u_b: float = 0.0
    u_c: float = 0.0
    i_a: float = 0.0
    i_b: float = 0.0
    i_c: float = 0.0
    p_a: float = 0.0
    p_b: float = 0.0
    p_c: float = 0.0
    P_total: float = 0.0
    Q_total: float = 0.0
    S_total: float = 0.0
    PF: float = 0.0
    f: float = 0.0
    imp_pt_today: float = 0.0
    exp_pt_today: float = 0.0
    imp_pt_total: float = 0.0
    exp_pt_total: float = 0.0
    created_at: Optional[str] = None