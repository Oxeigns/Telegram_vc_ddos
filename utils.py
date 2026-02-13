"""
Utility functions for safe network operations and validation
Final Optimized Version (10/10)
"""

import socket
import logging
import ipaddress
import re
from typing import Optional, Tuple, Union
from urllib.parse import urlparse

# Logging setup
logger = logging.getLogger(__name__)

# Constants
IP_SERVICES = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
    "https://icanhazip.com",
    "https://ident.me"
]

# IP Validation Regex (Strict)
IP_PATTERN = r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[a-fA-F0-9]{1,4}:){7}[a-fA-F0-9]{1,4}\b'

# ----------------------------
# NETWORK VALIDATION
# ----------------------------

def is_valid_ip(ip: str) -> bool:
    """Validate IPv4 or IPv6 address strictly."""
    if not ip or not isinstance(ip, str):
        return False
    try:
        ipaddress.ip_address(ip.strip())
        return True
    except ValueError:
        return False

def is_valid_port(port: Union[int, str]) -> bool:
    """Validate port number range (1-65535)."""
    try:
        p = int(port)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False

def resolve_hostname(hostname: str) -> Optional[str]:
    """Resolve hostname to IP safely with error handling."""
    if not hostname:
        return None
    try:
        return socket.gethostbyname(hostname.strip())
    except (socket.gaierror, socket.herror) as e:
        logger.warning(f"Resolution failed for {hostname}: {e}")
        return None

# ----------------------------
# PUBLIC IP DETECTION (FIXED)
# ----------------------------

def get_public_ip() -> Optional[str]:
    """
    Fetches real public IP using multiple fallbacks and strict Regex.
    Works even if services return HTML or extra text.
    """
    import requests
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    with requests.Session() as session:
        session.headers.update(headers)
        
        for url in IP_SERVICES:
            try:
                # Short timeout to skip dead services fast
                response = session.get(url, timeout=4)
                if response.status_code == 200:
                    raw_content = response.text.strip()
                    
                    # Regex se sirf IP extract karna (Real IP fix)
                    found_ips = re.findall(IP_PATTERN, raw_content)
                    
                    if found_ips:
                        ip = found_ips[0]
                        if is_valid_ip(ip):
                            return ip
                            
            except requests.RequestException:
                continue

    logger.error("Critical: All Public IP services failed.")
    return None

# ----------------------------
# PARSERS
# ----------------------------

def parse_ip_port(text: str) -> Optional[Tuple[str, int]]:
    """
    Parses IP:PORT strings. Supports IPv4, IPv6 [brackets], and Hostnames.
    Example: '192.168.1.1:80' or '[2001:db8::1]:443'
    """
    if not text or ':' not in text:
        return None

    text = text.strip()
    try:
        if text.startswith('['): # IPv6 Case
            if ']:' not in text: return None
            ip_part, port_part = text.split(']:')
            ip = ip_part.lstrip('[')
        else: # IPv4 or Hostname Case
            ip, port_part = text.rsplit(':', 1)

        port = int(port_part)
        
        if (is_valid_ip(ip) or len(ip) > 2) and is_valid_port(port):
            return ip, port

    except (ValueError, IndexError):
        pass
    return None

def parse_telegram_invite_link(text: str) -> Optional[str]:
    """
    Extracts Telegram handle/hash from links or usernames.
    Supports: @user, t.me/joinchat/hash, t.me/+hash, tg://join?invite=hash
    """
    if not text:
        return None

    text = text.strip()
    if text.startswith('@'):
        return text[1:]

    # Regex for t.me, telegram.me and tg:// protocols
    regex = r"(?:https?:\/\/)?(?:t(?:elegram)?\.me\/|tg:\/\/join\?invite=)([^/?\s]+)"
    match = re.search(regex, text)
    
    path = match.group(1) if match else text.replace('t.me/', '')

    if 'joinchat/' in path:
        return path.split('joinchat/')[1]
    
    # Remove leading + if it's a private hash link
    # Or just return the username/path
    return path.split('/')[0] if path else None

# ----------------------------
# FORMATTING & HELPERS
# ----------------------------

def format_number(num: Union[int, float, str]) -> str:
    """Format large numbers with commas (10000 -> 10,000)."""
    try:
        return f"{int(float(num)):,}"
    except (ValueError, TypeError):
        return str(num)

def calculate_success_rate(success: int, total: int) -> float:
    """Safely calculate percentage."""
    if not isinstance(success, int) or not isinstance(total, int) or total <= 0:
        return 0.0
    return round((success / total) * 100, 2)

def truncate_string(text: str, max_length: int = 50) -> str:
    """Truncate long strings with ellipsis."""
    if not text: return ""
    text = text.strip()
    return (text[:max_length-3] + "...") if len(text) > max_length else text
