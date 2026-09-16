"""
communication/modbus_tcp.py
Modbus TCP Transport Layer
Compatible with pymodbus 2.x and 3.x
"""

import time
import logging

from typing import Any
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException

from backend.communication.modbus_arbiter import ModbusBusArbiter


logger = logging.getLogger(__name__)


class ModbusTCP:
    def __init__(
        self,
        host: str,
        port: int = 502,
        timeout: float = 3.0,
        retries: int = 2,
    ):
        self.host = host
        self.port = port
        self.retries = retries
        self.arbiter = ModbusBusArbiter(f"tcp://{host}:{port}")
        self.last_failed_connect_time = 0.0
        self.reconnect_cooldown = 0.5  # Giãn cách tối thiểu giữa các lần kết nối lại (0.5s)
        self._slave_kwarg = "slave"

        self.client = ModbusTcpClient(
            host=host,
            port=port,
            timeout=timeout,
        )

    def connect(self, force: bool = False) -> bool:
        now = time.time()
        if not force and (now - self.last_failed_connect_time < self.reconnect_cooldown):
            logger.debug(f"[TCP] Cooldown active for {self.host}:{self.port}. Skipping connect attempt.")
            return False

        try:
            if not self.client.connect():
                logger.error(f"[TCP] Cannot connect to {self.host}:{self.port}")
                self.last_failed_connect_time = now
                return False
            logger.info(f"[TCP] Connected to {self.host}:{self.port}")
            self.last_failed_connect_time = 0.0
            return True
        except Exception as e:
            logger.error(f"[TCP] Connect error {self.host}:{self.port} -> {e}")
            self.last_failed_connect_time = now
            return False

    def close(self):
        try:
            self.client.close()
            logger.info(f"[TCP] Connection closed {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"[TCP] Close error: {e}")

    def _retry(self, func_name: str, address: int, count_or_val: Any, slave: int = 1):
        last_error = None

        self.arbiter.acquire()
        try:
            for attempt in range(1, self.retries + 1):
                try:
                    if not getattr(self.client, "connected", False):
                        if not self.connect(force=True if attempt > 1 else False):
                            raise ConnectionError(f"[TCP] Reconnect failed to {self.host}:{self.port}")

                    func = getattr(self.client, func_name)
                    kw = {self._slave_kwarg: slave}
                    try:
                        response = func(address, count_or_val, **kw)
                    except TypeError:
                        self._slave_kwarg = "unit" if self._slave_kwarg == "slave" else "slave"
                        kw = {self._slave_kwarg: slave}
                        response = func(address, count_or_val, **kw)

                    if isinstance(response, ModbusIOException) or (hasattr(response, "isError") and response.isError()):
                        last_error = response
                        logger.warning(
                            f"[TCP] Attempt {attempt}/{self.retries} error at slave {slave}: {response}"
                        )
                        self.close()
                        time.sleep(0.15)
                        continue

                    return response

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"[TCP] Attempt {attempt}/{self.retries} exception at slave {slave}: {e}"
                    )
                    self.close()
                    time.sleep(0.15)
        finally:
            self.arbiter.release()

        raise ConnectionError(
            f"[TCP] Communication failed after {self.retries} retries: {last_error}"
        )

    def read_input_registers(self, address: int, count: int, slave: int = 1):
        return self._retry("read_input_registers", address, count, slave=slave)

    def read_holding_registers(self, address: int, count: int, slave: int = 1):
        return self._retry("read_holding_registers", address, count, slave=slave)

    def write_single_register(self, address: int, value: int, slave: int = 1):
        return self._retry("write_register", address, int(value) & 0xFFFF, slave=slave)

    def write_multiple_registers(self, address: int, values, slave: int = 1):
        return self._retry("write_registers", address, values, slave=slave)

    def write_register(self, address: int, value: int, slave: int = 1):
        return self.write_single_register(address, value, slave=slave)
