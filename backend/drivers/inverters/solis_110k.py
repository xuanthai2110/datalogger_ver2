# drivers/solis_110k.py

import logging
from typing import Dict, Any
from backend.drivers.inverters.base import BaseDriver

logger = logging.getLogger(__name__)

class Solis110k(BaseDriver):

    def __init__(self, transport, slave_id=1):
        self.transport = transport
        self.slave_id = slave_id
        self.model = "110K"

    # =========================================================
    # ================= REGISTER MAP ==========================
    # =========================================================

    def register_map(self) -> Dict[str, Any]:

        return {

            "info": [
                {"name": "product_model", "address": 2999, "length": 1, "type": "uint16", "scale": None},
                {"name": "dsp_version", "address": 3000, "length": 1, "type": "uint16", "scale": None},
                {"name": "lcd_version", "address": 3001, "length": 1, "type": "uint16", "scale": None},
                {"name": "sn_1", "address": 3060, "length": 1, "type": "uint16", "scale": None},
                {"name": "sn_2", "address": 3061, "length": 1, "type": "uint16", "scale": None},
                {"name": "sn_3", "address": 3062, "length": 1, "type": "uint16", "scale": None},
                {"name": "sn_4", "address": 3063, "length": 1, "type": "uint16", "scale": None},
            ],

            "ac": [
                {"name": "v_a", "address": 3033, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "v_b", "address": 3034, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "v_c", "address": 3035, "length": 1, "type": "uint16", "scale": 0.1},

                {"name": "i_a", "address": 3036, "length": 1, "type": "uint16", "scale": 0.1},    
                {"name": "i_b", "address": 3037, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "i_c", "address": 3038, "length": 1, "type": "uint16", "scale": 0.1},

                {"name": "p_inv_w", "address": 3004, "length": 2, "type": "uint32", "scale": 1},
                {"name": "q_inv_var", "address": 3055, "length": 2, "type": "sint32", "scale": 1},
                {"name": "pf", "address": 3050, "length": 1, "type": "sint16", "scale": 0.001},
                {"name": "grid_hz", "address": 3042, "length": 1, "type": "uint16", "scale": 0.01},
            ],

            "dc": [
                {"name": "p_dc_w", "address": 3006, "length": 2, "type": "uint32", "scale": 1},

                {"name": "mppt_1_voltage", "address": 3499, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_2_voltage", "address": 3500, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_3_voltage", "address": 3501, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_4_voltage", "address": 3502, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_5_voltage", "address": 3503, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_6_voltage", "address": 3504, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_7_voltage", "address": 3505, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_8_voltage", "address": 3506, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_9_voltage", "address": 3507, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_10_voltage", "address": 3508, "length": 1, "type": "uint16", "scale": 0.1},

                {"name": "mppt_1_current", "address": 3529, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_2_current", "address": 3530, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_3_current", "address": 3531, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_4_current", "address": 3532, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_5_current", "address": 3533, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_6_current", "address": 3534, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_7_current", "address": 3535, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_8_current", "address": 3536, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_9_current", "address": 3537, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "mppt_10_current", "address": 3538, "length": 1, "type": "sint16", "scale": 0.1},
            ],

            "string": [
                {
                    "name": f"string_{i}_current",
                    "address": 3299 + i,
                    "length": 1,
                    "type": "sint16",
                    "scale": 0.1
                }
                for i in range(1, 21)
            ],

            "stat": [
                {"name": "temp_c",   "address": 3041, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "ir",       "address": 3091, "length": 1, "type": "uint16", "scale": 1},
                {"name": "e_daily",  "address": 3014, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "e_total",  "address": 3008, "length": 2, "type": "uint32", "scale": 1},
            ],
            
            "control": [
                {"name": "power_limit_switch", "address": 3069, "length": 1, "type": "uint16", "scale": None},
                {"name": "power_limit_value", "address": 3080, "length": 1, "type": "sint16", "scale": 10},
            ]

        }

    # =========================================================
    # ================= MODBUS READ ===========================
    # =========================================================

    def _read_input_block(self, start: int, length: int):
        response = self.transport.read_input_registers(
            address=start,
            count=length,
            slave=self.slave_id
        )

        if response.isError():
            raise Exception("Modbus read input error")

        return response.registers

    def _read_holding_block(self, start: int, length: int):
        response = self.transport.read_holding_registers(
            address=start,
            count=length,
            slave=self.slave_id
        )

        if response.isError():
            raise Exception("Modbus read holding error")

        return response.registers

    def _group_contiguous(self, regs: list[dict]) -> list[list[dict]]:
        if not regs:
            return []

        ordered_regs = sorted(regs, key=lambda reg: reg["address"])
        groups = [[ordered_regs[0]]]

        for reg in ordered_regs[1:]:
            previous = groups[-1][-1]
            previous_end = previous["address"] + previous["length"]
            if reg["address"] == previous_end:
                groups[-1].append(reg)
            else:
                groups.append([reg])

        return groups

    def _read_group(self, regs: list[dict], read_kind: str = "input") -> Dict[str, Any]:
        if not regs:
            return {}

        result = {}
        reader = self._read_input_block if read_kind == "input" else self._read_holding_block

        for group in self._group_contiguous(regs):
            start = group[0]["address"]
            end = max(reg["address"] + reg["length"] - 1 for reg in group)
            raw = reader(start, end - start + 1)

            ordered = []
            for reg in group:
                idx = reg["address"] - start
                ordered.extend(raw[idx: idx + reg["length"]])

            result.update(self.parse(ordered, group))

        return result

    # =========================================================
    # ================= PARSER ================================
    # =========================================================

    def _convert(self, registers, data_type):

        if not registers:
            return None

        if data_type == "uint16":
            return registers[0] & 0xFFFF

        if data_type == "sint16":
            v = registers[0] & 0xFFFF
            if v & 0x8000:
                v -= 0x10000
            return v

        # Word order: high word first

        if data_type == "uint32":
            high = registers[0]
            low = registers[1]
            return ((high & 0xFFFF) << 16) | (low & 0xFFFF)

        if data_type == "sint32":
            high = registers[0]
            low = registers[1]

            v = ((high & 0xFFFF) << 16) | (low & 0xFFFF)

            if v & 0x80000000:
                v -= 0x100000000

            return v

        return None

    # =========================================================
    # ================= PARSE BLOCK ===========================
    # =========================================================

    def parse(self, raw_block: Dict[str, Any], reg_list: list = None) -> Dict[str, Any]:
        if reg_list is None:
            return {}

        result = {}
        offset = 0

        for reg in reg_list:

            length = reg["length"]

            raw = raw_block[offset: offset + length]

            value = self._convert(raw, reg["type"])

            if value is not None and reg["scale"] is not None:
                value *= reg["scale"]

            result[reg["name"]] = value

            offset += length

        return result

    # =========================================================
    # ================= READ GROUPS ===========================
    # =========================================================

    def read_info(self) -> Dict[str, Any]:
        from datetime import datetime
        try:
            regs = self.register_map()["info"]
            parsed = self._read_group(regs)

            # Convert registers to hex string serial number with byte & nibble swap
            sn = ""
            for i in range(1, 5):
                val = parsed.get(f"sn_{i}")
                if val is not None:
                    val_int = int(val) & 0xFFFF
                    # Tách byte cao và byte thấp
                    high = (val_int >> 8) & 0xFF
                    low = val_int & 0xFF
                    # Đảo vị trí 4 bit (nibble swap) của từng byte
                    high_swapped = ((high & 0x0F) << 4) | ((high & 0xF0) >> 4)
                    low_swapped = ((low & 0x0F) << 4) | ((low & 0xF0) >> 4)
                    # Ghép lại theo thứ tự đảo byte (byte thấp đã swapped đứng trước)
                    correct_val = (low_swapped << 8) | high_swapped
                    sn += f"{correct_val:04X}"

            # Solis 110kW defaults
            rate_ac = 110.0
            rate_dc = 110.0

            return {
                "brand": "Solis",
                "model": "110K",
                "serial_number": sn[:15],
                "capacity_kw": rate_ac,
                "mppt_count": 10,
                "firmware_version": str(parsed.get("dsp_version", "1.0")),
                "phase_count": 3,
                "strings_per_mppt": 2,
                "string_count": 20,
                "rate_dc_kwp": rate_dc,
                "rate_ac_kw": rate_ac,
                "is_active": True,
                "slave_id": self.slave_id,
                "usage_start_at": datetime.now().isoformat(),
                "usage_end_at": None,
                "replaced_by_id": None
            }
        except Exception as e:
            return {
                "brand": "Solis",
                "model": "110K",
                "serial_number": "",
                "capacity_kw": 110.0,
                "mppt_count": 10,
                "firmware_version": "1.0",
                "phase_count": 3,
                "strings_per_mppt": 2,
                "string_count": 20,
                "rate_dc_kwp": 110.0,
                "rate_ac_kw": 110.0,
                "is_active": False,
                "slave_id": self.slave_id,
                "usage_start_at": datetime.now().isoformat(),
                "usage_end_at": None,
                "replaced_by_id": None
            }

    def read_ac(self) -> Dict[str, Any]:
        return self._read_group(self.register_map()["ac"])

    def read_dc(self) -> Dict[str, Any]:
        return self._read_group(self.register_map()["dc"])

    def read_string(self) -> Dict[str, Any]:
        return self._read_group(self.register_map()["string"])

    def read_stat(self) -> Dict[str, Any]:
        regs = self.register_map().get("stat", [])
        return self._read_group(regs) if regs else {}

    # =========================================================
    # ================= FAULTS & STATES =======================
    # =========================================================

    def read_states_and_faults(self) -> Dict[str, Any]:
        # Read working status (3044 -> address 3043)
        res_state = self.transport.read_input_registers(
            address=3043,
            count=1,
            slave=self.slave_id
        )
        state_id = 0
        if not res_state.isError():
            state_id = res_state.registers[0]

        # Read Fault codes 01-05 (3067-3071 -> address 3066-3070)
        res_fault = self.transport.read_input_registers(
            address=3066,
            count=5,
            slave=self.slave_id
        )
        fault_code_1 = 0
        fault_code_2 = 0
        fault_code_3 = 0
        fault_code_4 = 0
        fault_code_5 = 0
        if not res_fault.isError() and len(res_fault.registers) >= 5:
            fault_code_1 = res_fault.registers[0]
            fault_code_2 = res_fault.registers[1]
            fault_code_3 = res_fault.registers[2]
            fault_code_4 = res_fault.registers[3]
            fault_code_5 = res_fault.registers[4]

        return {
            "state_id": state_id,
            "fault_code": fault_code_1,
            "fault_code_1": fault_code_1,
            "fault_code_2": fault_code_2,
            "fault_code_3": fault_code_3,
            "fault_code_4": fault_code_4,
            "fault_code_5": fault_code_5,
        }


    # =========================================================
    # ================= READ ALL ==============================
    # =========================================================

    def read_all(self) -> Dict[str, Any]:
        data = {}

        data.update(self.read_info())
        data.update(self.read_ac())

        dc = self.read_dc()
        strings = self.read_string()

        data.update(dc)
        data.update(strings)

        try:
            data.update(self.read_stat())
        except Exception:
            pass

        try:
            states_and_faults = self.read_states_and_faults()
            data.update(states_and_faults)
        except Exception:
            pass

        return data


    # =========================================================
    # ================= CONTROL ===============================
    # =========================================================

    def enable_power_limit(self, enable: bool) -> bool:
        # Write limit switch (3070 -> address 3069): 0xAA (ON) / 0x55 (OFF)
        val = 0x00AA if enable else 0x0055
        response = self.transport.write_register(
            address=3069,
            value=val,
            slave=self.slave_id
        )
        return self._ensure_write_ok(response, f"Enable power limit {enable}")

    def write_power_limit_kw(self, kw: float) -> bool:
        return self.set_power_kw(kw)

    def write_power_limit_percent(self, percent: float) -> bool:
        return self.set_power_percent(percent)


    @staticmethod
    def _ensure_write_ok(response, action: str) -> bool:
        if response is None:
            raise Exception(f"{action} returned no response")
        if hasattr(response, "isError") and response.isError():
            raise Exception(f"{action} failed: {response}")
        return True

    def set_power_percent(self, percent):
        # 110kW capacity -> percent limit
        # Convert percent to Watt, then Solis uses 10W limit values
        watt = (percent / 100.0) * 110000.0
        return self.set_power_w(watt)

    def set_power_kw(self, kw):
        return self.set_power_w(kw * 1000.0)

    def set_power_w(self, watt):
        # Solis uses 10W steps, S16 value
        val_10w = int(round(watt / 10.0))
        
        # Ensure it fits S16
        if val_10w < 0:
            val_10w = (1 << 16) + val_10w
            
        # First, ensure power limit is enabled
        self.enable_power_limit(True)

        response = self.transport.write_register(
            address=3080,
            value=val_10w,
            slave=self.slave_id
        )

        return self._ensure_write_ok(response, f"Write watt limit {watt}")

    def read_power_limit(self):
        res_switch = self.transport.read_holding_registers(
            address=3069,
            count=1,
            slave=self.slave_id
        )
        if res_switch.isError():
            raise Exception(f"Read power limit switch failed: {res_switch}")

        res_val = self.transport.read_holding_registers(
            address=3080,
            count=1,
            slave=self.slave_id
        )
        if res_val.isError():
            raise Exception(f"Read power limit value failed: {res_val}")

        mode = res_switch.registers[0]
        val_10w = res_val.registers[0]
        
        if val_10w & 0x8000:
            val_10w -= 0x10000

        return {
            "mode": mode,
            "limit_w": val_10w * 10
        }

    def read_power(self):
        # Read Active power from 3005-3006 (address 3004)
        res = self.transport.read_input_registers(
            address=3004,
            count=2,
            slave=self.slave_id
        )

        if res.isError():
            raise Exception(f"Read inverter power failed: {res}")

        regs = res.registers

        value = (regs[0] << 16) + regs[1]

        if value > 0x7FFFFFFF:
            value -= 0x100000000

        return value

    def read_power_limit_percent(self) -> float:
        try:
            limit = self.read_power_limit()
            if limit.get("mode") == 0xAA:
                return (limit.get("limit_w", 110000.0) / 110000.0) * 100.0
            return 100.0
        except Exception:
            return 100.0
