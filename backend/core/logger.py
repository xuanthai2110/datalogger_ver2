import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from backend.core import settings

_logging_configured = False

def setup_logging():
    """
    Cấu hình logging toàn cục cho hệ thống (thiết lập trên Root Logger).
    Hỗ trợ in ra Console (StreamHandler) và ghi log xoay vòng ra file (RotatingFileHandler).
    """
    global _logging_configured
    if _logging_configured:
        return
        
    root_logger = logging.getLogger()
    
    # Thiết lập level log mặc định là INFO
    root_logger.setLevel(logging.INFO)
    
    # Formatter chuẩn của hệ thống
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Xóa các handler cũ nếu có để tránh trùng lặp log
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
        
    # 1. Console Handler (StreamHandler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 2. File Handler với cơ chế xoay vòng (Log Rotation)
    # File log được đặt tại thư mục: PROJECT_ROOT/logs/datalogger.log
    try:
        log_dir = Path(settings.PROJECT_ROOT) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "datalogger.log"
        
        # Cấu hình xoay vòng: 10MB mỗi file, tối đa 5 file backup cũ
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
    except Exception as e:
        # Fallback nếu không tạo được thư mục hoặc tệp log (ví dụ: lỗi quyền ghi)
        print(f"[LoggerSetup] Warning: Could not setup file log rotation: {e}")
        
    _logging_configured = True

def get_logger(name="datalogger"):
    """
    Đảm bảo logging đã được cấu hình và trả về logger với tên chỉ định.
    """
    setup_logging()
    return logging.getLogger(name)