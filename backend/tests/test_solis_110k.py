#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import argparse
import pprint

# Thêm thư mục hiện tại vào System Path để có thể import backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.communication.modbus_rtu import ModbusRTU
from backend.drivers.inverters.solis_110k import Solis110k

def main():
    parser = argparse.ArgumentParser(description="Script test đọc dữ liệu Modbus RTU từ Inverter Solis 110K.")
    parser.add_argument("-p", "--port", default="/dev/ttyUSB0", help="Cổng Serial kết nối (ví dụ: /dev/ttyUSB0 hoặc COM1)")
    parser.add_argument("-b", "--baud", type=int, default=9600, help="Tốc độ Baudrate (mặc định: 9600)")
    parser.add_argument("-s", "--slave", type=int, default=2, help="Địa chỉ Modbus Slave ID của Inverter (mặc định: 2)")
    
    args = parser.parse_args()
    
    print("=========================================================================")
    print("                 TEST DRIVER INVERTER SOLIS 110K                         ")
    print("=========================================================================")
    print(f"[*] Cổng kết nối vật lý: {args.port}")
    print(f"[*] Tốc độ Baud        : {args.baud}")
    print(f"[*] Modbus Slave ID    : {args.slave}")
    print("=========================================================================")
    
    # 1. Khởi tạo kết nối Modbus RTU
    rtu = ModbusRTU(
        port=args.port,
        baudrate=args.baud,
        parity="N",
        stopbits=1,
        bytesize=8,
        timeout=1.5,
        retries=3,
        multi_master=False
    )
    
    # 2. Khởi tạo Driver Solis 110K
    driver = Solis110k(transport=rtu, slave_id=args.slave)
    
    if not rtu.connect():
        print(f"[-] LỖI: Không thể mở cổng Serial {args.port}. Vui lòng kiểm tra kết nối hoặc quyền truy cập!")
        sys.exit(1)
        
    try:
        # 3. Đọc thông tin cơ bản (Info)
        print("\n[*] Đang đọc thông tin thiết bị (read_info)...")
        info = driver.read_info()
        print("[+] Kết quả read_info():")
        pprint.pprint(info)
        
        # 4. Đọc toàn bộ tham số thời gian thực (Read All)
        print("\n[*] Đang đọc toàn bộ dữ liệu (read_all)...")
        data = driver.read_all()
        print("[+] Kết quả read_all():")
        pprint.pprint(data)
        
    except Exception as e:
        print(f"[-] LỖI trong quá trình giao tiếp Modbus: {e}")
    finally:
        rtu.close()
        print("\n[*] Đã đóng cổng Serial. Kết thúc test.")

if __name__ == "__main__":
    main()
