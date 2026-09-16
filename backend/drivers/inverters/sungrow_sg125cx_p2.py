"""
Proxy module to support both filename conventions:
- sungrow_sg125cxp2.py
- sungrow_sg125cx_p2.py
"""
from backend.drivers.sungrow_sg125cxp2 import (
    Sungrowsg125cxp2,
    SungrowSG125CXP2,
)

# Class name expected by scan_api for model "SG125CX-P2":
# brand.capitalize() + model.replace("-", "").replace(".", "").lower() -> "Sungrowsg125cxp2"
# or model.lower().replace("-", "_") -> module name "sungrow_sg125cx_p2"
Sungrowsg125cxp2 = Sungrowsg125cxp2
Sungrowsg125cx_p2 = Sungrowsg125cxp2
SungrowSG125CXP2 = SungrowSG125CXP2
