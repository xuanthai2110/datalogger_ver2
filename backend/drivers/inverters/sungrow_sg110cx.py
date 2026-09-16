from typing import Dict, Any

from backend.drivers.inverters.base import BaseDriver


class Sungrowsg110cx(BaseDriver):
    def __init__(self, transport, slave_id: int):
        self.transport = transport
        self.slave_id = slave_id

    # =========================================================
    # ================= REGISTER MAP ==========================
    # =========================================================

    def register_map(self) -> Dict[str, Any]:
        return {
            "info": [
                {"name": "serial_number", "address": 4989, "length": 10, "type": "string", "scale": None},
                {"name": "type_code", "address": 4999, "length": 1, "type": "uint16", "scale": None},
                {"name": "rated_power", "address": 5000, "length": 1, "type": "uint16", "scale": 0.1},
            ],
            "ac": [
                {"name": "v_a", "address": 5018, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "v_b", "address": 5019, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "v_c", "address": 5020, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "i_a", "address": 5021, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "i_b", "address": 5022, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "i_c", "address": 5023, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "p_inv_w", "address": 5030, "length": 2, "type": "uint32", "scale": 1},
                {"name": "q_inv_var", "address": 5032, "length": 2, "type": "sint32", "scale": 1},
                {"name": "pf", "address": 5034, "length": 1, "type": "sint16", "scale": 0.001},
                {"name": "grid_hz", "address": 5147, "length": 1, "type": "uint16", "scale": 0.01},
            ],
            "dc": [
                {"name": "p_dc_w", "address": 5016, "length": 2, "type": "uint32", "scale": 1},
                {"name": "mppt_1_voltage", "address": 5010, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_1_current", "address": 5011, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_2_voltage", "address": 5012, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_2_current", "address": 5013, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_3_voltage", "address": 5014, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_3_current", "address": 5015, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_4_voltage", "address": 5114, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_4_current", "address": 5115, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_5_voltage", "address": 5116, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_5_current", "address": 5117, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_6_voltage", "address": 5118, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_6_current", "address": 5119, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_7_voltage", "address": 5120, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_7_current", "address": 5121, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_8_voltage", "address": 5122, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_8_current", "address": 5123, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_9_voltage", "address": 5129, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "mppt_9_current", "address": 5130, "length": 1, "type": "uint16", "scale": 0.1},
            ],
            "string": [
                {
                    "name": f"string_{i}_current",
                    "address": 7011 + i,
                    "length": 1,
                    "type": "uint16",
                    "scale": 0.01,
                }
                for i in range(1, 19)
            ],
            "stat": [
                {"name": "temp_c", "address": 5007, "length": 1, "type": "sint16", "scale": 0.1},
                {"name": "e_daily", "address": 5002, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "e_total", "address": 5143, "length": 2, "type": "uint32", "scale": 0.1},
                {"name": "ir", "address": 5070, "length": 1, "type": "uint16", "scale": 1.0},
            ],
            "control": [
                {"name": "enable_power_limit", "address": 5006, "length": 1, "type": "uint16", "scale": None},
                {"name": "power_limit_percent", "address": 5007, "length": 1, "type": "uint16", "scale": 0.1},
                {"name": "power_limit_kw", "address": 5038, "length": 1, "type": "uint16", "scale": 0.1},
            ],
        }

    # =========================================================
    # ================= LOW LEVEL READ ========================
    # =========================================================

    def _read_input(self, start: int, length: int):
        response = self.transport.read_input_registers(
            address=start,
            count=length,
            slave=self.slave_id,
        )
        if response.isError():
            raise Exception(f"Modbus read_input_registers error at {start}")
        return response.registers

    def _read_holding(self, start: int, length: int):
        response = self.transport.read_holding_registers(
            address=start,
            count=length,
            slave=self.slave_id,
        )
        if response.isError():
            raise Exception(f"Modbus read_holding_registers error at {start}")
        return response.registers

    def _read_block(self, start: int, length: int):
        return self._read_input(start, length)

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
        reader = self._read_input if read_kind == "input" else self._read_holding

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

        # Sungrow word order: low word first
        if data_type == "uint32":
            if len(registers) < 2:
                return None
            low = registers[0]
            high = registers[1]
            return ((high & 0xFFFF) << 16) | (low & 0xFFFF)

        if data_type == "sint32":
            if len(registers) < 2:
                return None
            low = registers[0]
            high = registers[1]
            v = ((high & 0xFFFF) << 16) | (low & 0xFFFF)
            if v & 0x80000000:
                v -= 0x100000000
            return v

        if data_type == "string":
            raw_bytes = bytearray()
            for reg in registers:
                high = (reg >> 8) & 0xFF
                low = reg & 0xFF
                raw_bytes.append(high)
                raw_bytes.append(low)
            return raw_bytes.decode("utf-8", errors="ignore").rstrip("\x00").strip()

        return None

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
            parsed = self._read_group(self.register_map()["info"])
            rated_kw = parsed.get("rated_power", 110.0) or 110.0

            return {
                "brand": "Sungrow",
                "model": "SG110CX",
                "serial_number": parsed.get("serial_number", ""),
                "type_code": parsed.get("type_code"),
                "capacity_kw": rated_kw,
                "mppt_count": 9,
                "firmware_version": "1.0",
                "phase_count": 3,
                "strings_per_mppt": 2,
                "string_count": 18,
                "rate_dc_kwp": rated_kw,
                "rate_ac_kw": rated_kw,
                "is_active": True,
                "slave_id": self.slave_id,
                "usage_start_at": datetime.now().isoformat(),
                "usage_end_at": None,
                "replaced_by_id": None,
            }
        except Exception:
            return {
                "brand": "Sungrow",
                "model": "SG110CX",
                "serial_number": "",
                "capacity_kw": 110.0,
                "mppt_count": 9,
                "firmware_version": "1.0",
                "phase_count": 3,
                "strings_per_mppt": 2,
                "string_count": 18,
                "rate_dc_kwp": 110.0,
                "rate_ac_kw": 110.0,
                "is_active": False,
                "slave_id": self.slave_id,
                "usage_start_at": datetime.now().isoformat(),
                "usage_end_at": None,
                "replaced_by_id": None,
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

    def read_power(self) -> int:
        """AC inverter power in watts (input `p_inv_w`, address 5030; same as register_map ac)."""
        regs = self._read_input(5030, 2)
        value = self._convert(regs, "uint32")
        if value is None:
            raise Exception("read_power: invalid register data")
        return int(value)

    # =========================================================
    # ================= FAULTS & STATES =======================
    # =========================================================

    def read_states_and_faults(self) -> Dict[str, Any]:
        state_id = 0
        fault_code = 0

        res_state = self.transport.read_input_registers(
            address=5037,
            count=1,
            slave=self.slave_id,
        )
        if not res_state.isError():
            state_id = res_state.registers[0]

        res_fault = self.transport.read_input_registers(
            address=5044,
            count=1,
            slave=self.slave_id,
        )
        if not res_fault.isError():
            fault_code = res_fault.registers[0]

        return {
            "state_id": state_id,
            "fault_code": fault_code,
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
            data.update(self.read_states_and_faults())
        except Exception:
            pass

        return data

    # =========================================================
    # ================= CONTROL ===============================
    # =========================================================

    @staticmethod
    def _ensure_write_ok(response, action: str) -> bool:
        if response is None:
            raise Exception(f"{action} returned no response")
        if hasattr(response, "isError") and response.isError():
            raise Exception(f"{action} failed: {response}")
        return True

    def enable_power_limit(self, enable: bool) -> bool:
        response = self.transport.write_register(
            address=5006,
            value=0xAA if enable else 0x55,
            slave=self.slave_id,
        )
        return self._ensure_write_ok(response, f"Enable power limit={enable}")

    def write_power_limit_kw(self, kw: float) -> bool:
        response = self.transport.write_register(
            address=5038,
            value=int(kw * 10),
            slave=self.slave_id,
        )
        return self._ensure_write_ok(response, f"Write kW limit {kw}")

    def write_power_limit_percent(self, percent: float) -> bool:
        response = self.transport.write_register(
            address=5007,
            value=int(percent * 10),
            slave=self.slave_id,
        )
        return self._ensure_write_ok(response, f"Write percent limit {percent}")

    def read_power_limit_percent(self) -> float:
        try:
            response = self.transport.read_holding_registers(
                address=5006,
                count=2,
                slave=self.slave_id,
            )
            if response.isError() or len(response.registers) < 2:
                return 100.0
            sw = response.registers[0]
            val = response.registers[1]
            if sw == 0xAA:
                return float(val) / 10.0
            return 100.0
        except Exception:
            return 100.0