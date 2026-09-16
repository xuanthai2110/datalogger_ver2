# backend/drivers/batteries/pylontech_bms.py

import logging
from typing import Dict, Any, Optional
from .base_battery_driver import BaseBatteryDriver

logger = logging.getLogger(__name__)

class PylontechBMSDriver(BaseBatteryDriver):
    """
    Driver đọc dữ liệu trực tiếp từ BMS Pin Pylontech (US2000 / US3000C / US5000 / Force-L2) qua RS485.
    """

    def __init__(self, transport, slave_id: int = 1):
        super().__init__(transport, slave_id=slave_id)

    def _read_registers(self, func_code: str, address: int, count: int):
        try:
            fn = getattr(self.transport, func_code, None)
            if callable(fn):
                resp = fn(address, count, slave=self.slave_id)
                if isinstance(resp, list):
                    return resp
                if hasattr(resp, 'registers') and isinstance(resp.registers, list):
                    return resp.registers
        except Exception as e:
            logger.debug(f"[PylontechBMS] Error reading {func_code} at {address}: {e}")
        return None

    def read_info(self) -> Optional[Dict[str, Any]]:
        """
        Đọc thông tin định danh trực tiếp từ BMS Pylontech.
        Mô phỏng đọc chuỗi Serial Number gốc từ thanh ghi 0-9 (ASCII).
        """
        raw_sn = self._read_registers('read_holding_registers', 0, 10)
        if not raw_sn:
            raw_sn = self._read_registers('read_input_registers', 0, 10)

        if not raw_sn:
            return None

        # Convert 16-bit register values to ASCII string if available
        sn_bytes = bytearray()
        for reg in raw_sn:
            sn_bytes.append((reg >> 8) & 0xFF)
            sn_bytes.append(reg & 0xFF)
        
        sn_str = sn_bytes.decode('ascii', errors='ignore').strip('\x00').strip()
        if not sn_str or len(sn_str) < 3:
            sn_str = f"PYLON_{self.slave_id:02d}_{sum(raw_sn)}"

        return {
            "serial_number": sn_str,
            "brand": "Pylontech",
            "model": "US5000",
            "capacity_kwh": 4.8,
            "capacity_ah": 100.0,
            "cells_per_module": 15,
            "modules_in_series": 1,
            "num_parallel_connections": 1,
            "is_active": True,
            "slave_id": self.slave_id
        }

    def read_telemetry(self) -> Optional[Dict[str, Any]]:
        """
        Đọc dữ liệu vận hành thời gian thực từ BMS Pylontech.
        Registers 16-24: Voltage (0.1V), Current (0.1A), SOC (%), SOH (%)
        """
        raw = self._read_registers('read_input_registers', 16, 10)
        if not raw or len(raw) < 6:
            return None

        u_val = raw[0] * 0.1
        i_val = ((raw[1] if raw[1] < 32768 else raw[1] - 65536)) * 0.1
        p_val = round(u_val * i_val, 2)
        soc = raw[4] if raw[4] <= 100 else 100
        soh = raw[5] if raw[5] <= 100 else 100
        temp = (raw[6] - 40.0) if len(raw) > 6 else 25.0

        info = self.read_info()
        sn = info["serial_number"] if info else f"PYLON_{self.slave_id}"

        return {
            "serial_number": sn,
            "inv_batt_u": u_val,
            "inv_batt_i": i_val,
            "inv_batt_p": p_val,
            "bms_batt_u": u_val,
            "bms_batt_i": i_val,
            "bms_batt_p": p_val,
            "bms_batt_soc": soc,
            "bms_batt_soh": soh,
            "bms_state": "NORMAL",
            "bms_min_cell_temp": temp,
            "bms_max_cell_temp": temp
        }
