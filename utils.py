import socket
import logging
import ipaddress
import re
import requests
from typing import Optional, Tuple, Union

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("HerokuUtils")

# ----------------------------
# NETWORK VALIDATION & IP TOOLS
# ----------------------------

def is_valid_ip(ip: str) -> bool:
    if not ip: return False
    try:
        ipaddress.ip_address(str(ip).strip())
        return True
    except: return False

def is_valid_port(port: Union[int, str]) -> bool:
    try: return 1 <= int(port) <= 65535
    except: return False

def get_public_ip() -> Optional[str]:
    # Heroku dyno ki IP dikhayega
    try:
        response = requests.get("https://api.ipify.org", timeout=5)
        return response.text if response.status_code == 200 else None
    except: return None

# ----------------------------
# PARSERS (Matches your bot_handler.py requirements)
# ----------------------------

def parse_ip_port(text: str) -> Optional[Tuple[str, int]]:
    """Parses 'IP:PORT' strings safely."""
    if not text or ':' not in text:
        return None
    try:
        text = text.strip()
        if text.startswith('['): # IPv6
            ip_part, port_part = text.split(']:')
            ip = ip_part.lstrip('[')
        else: # IPv4
            ip, port_part = text.rsplit(':', 1)
        
        port = int(port_part)
        if (is_valid_ip(ip) or len(ip) > 2) and is_valid_port(port):
            return ip, port
    except:
        pass
    return None

def parse_telegram_invite_link(text: str) -> Optional[str]:
    """Extracts username or hash from telegram links."""
    if not text: return None
    text = text.strip()
    # Regex to handle various telegram link formats
    regex = r"(?:https?:\/\/)?(?:t(?:elegram)?\.me\/|tg:\/\/join\?invite=)([^/?\s]+)"
    match = re.search(regex, text)
    if match:
        return match.group(1)
    return text.replace('@', '')

# ----------------------------
# FORMATTING HELPERS
# ----------------------------

def format_number(num: Union[int, float, str]) -> str:
    try:
        return f"{int(float(num)):,}"
    except:
        return str(num)

def calculate_success_rate(success: int, total: int) -> float:
    if not total or total <= 0: return 0.0
    return round((success / total) * 100, 2)

# ----------------------------
# VC IP HELPER (FOR BOT COMMAND)
# ----------------------------

def get_vc_ip_instruction() -> str:
    """
    Since Sniffing is impossible on Heroku, this provides the 
    alternative method to use through the bot.
    """
    return (
        "⚠️ **Note:** Heroku servers cannot sniff packets directly.\n\n"
        "**Method to get VC IP:**\n"
        "1. Open Wireshark on your Local PC.\n"
        "2. Join the VC and filter by `udp.length > 100`.\n"
        "3. Copy the most active IP and use `/attack IP:PORT`."
    )

if __name__ == "__main__":
    print("Bot Utilities Loaded for Heroku.")
