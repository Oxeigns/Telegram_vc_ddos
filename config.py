"""
Configuration - Termux Optimized
"""

import os


class Config:
    """Bot Configuration - Auto loads from .env"""
    
    # Telegram Bot
    API_ID: int = int(os.environ.get("API_ID", 35335474))
    API_HASH: str = os.environ.get("API_HASH", "65c9d8d32a75ba9af8cc401d940b5957")
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
    
    # Admin
    ADMIN_USER_ID: int = int(os.environ.get("ADMIN_USER_ID", 7440486652))
    
    # Attack Settings
    MAX_REQUESTS: int = int(os.environ.get("MAX_REQUESTS", 100000))
    THREAD_COUNT: int = int(os.environ.get("THREAD_COUNT", 100))
    ATTACK_TIMEOUT: int = int(os.environ.get("ATTACK_TIMEOUT", 300))
    
    # Bot Settings
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        errors = []
        
        if not cls.API_ID or cls.API_ID == 0:
            errors.append("API_ID missing")
        if not cls.API_HASH:
            errors.append("API_HASH missing")
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN missing")
        if not cls.ADMIN_USER_ID or cls.ADMIN_USER_ID == 0:
            errors.append("ADMIN_USER_ID missing")
        
        if errors:
            print(f"[ERROR] Missing: {', '.join(errors)}")
            print("[INFO] Create .env file with your credentials")
            return False
        
        print(f"[CONFIG] ✓ Admin: {cls.ADMIN_USER_ID}")
        print(f"[CONFIG] ✓ Threads: {cls.THREAD_COUNT}")
        print(f"[CONFIG] ✓ Max Requests: {cls.MAX_REQUESTS:,}")
        return True


# Attack Methods Info
ATTACK_METHODS = {
    "udp": {"name": "UDP Flood", "description": "High-volume UDP packets"},
    "tcp": {"name": "TCP SYN", "description": "TCP connection flood"},
    "http": {"name": "HTTP Flood", "description": "HTTP GET flood"},
}
