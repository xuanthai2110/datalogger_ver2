"""
backend/drivers/acrel_dtsd1352_c.py — Driver thừa kế cho Acrel DTSD1352-C.
"""

from backend.drivers.meters.acrel_dtsd1352 import MeterAcreldtsd1352


class MeterAcreldtsd1352c(MeterAcreldtsd1352):
    """
    Class này thừa kế từ MeterAcreldtsd1352 để tương thích động với model 'DTSD1352-C' / 'DTSD1352_C'.
    """
    pass
