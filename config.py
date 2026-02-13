"""
Configuration for Network Stress Test Bot
"""

import os


class Config:
    """Bot Configuration"""
    
    # Telegram Bot (Only Bot Token needed - no user session)
    API_ID: int = int(os.environ.get("API_ID", 0))
    API_HASH: str = os.environ.get("API_HASH", "")
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
    
    # Admin
    ADMIN_USER_ID: int = int(os.environ.get("ADMIN_USER_ID", 0))
    
    # Attack Settings
    MAX_REQUESTS: int = int(os.environ.get("MAX_REQUESTS", 100000))
    THREAD_COUNT: int = int(os.environ.get("THREAD_COUNT", 100))
    ATTACK_TIMEOUT: int = int(os.environ.get("ATTACK_TIMEOUT", 300))
    
    # Bot Settings
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        required = ["API_ID", "API_HASH", "BOT_TOKEN", "ADMIN_USER_ID"]
        missing = []
        
        for key in required:
            value = getattr(cls, key)
            if not value or value == 0:
                missing.append(key)
        
        if missing:
            print(f"[ERROR] Missing: {', '.join(missing)}")
            return False
        
        print(f"[CONFIG] Loaded - Admin: {cls.ADMIN_USER_ID}")
        print(f"[CONFIG] Threads: {cls.THREAD_COUNT}, Max Requests: {cls.MAX_REQUESTS:,}")
        return True


# Attack Methods
ATTACK_METHODS = {
    "udp": {"name": "UDP Flood", "description": "High-volume UDP packets"},
    "tcp": {"name": "TCP SYN", "description": "TCP connection flood"},
    "slowloris": {"name": "Slowloris", "description": "Slow HTTP connections"},
}
