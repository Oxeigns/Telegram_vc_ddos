"""
Utility functions for safe network operations and validation
Optimized & Robust Version
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
]

# ----------------------------
# IP & NETWORK VALIDATION
# ----------------------------

def is_valid_ip(ip: str) -> bool:
    """Validate IPv4 or IPv6 address using ipaddress module."""
    if not ip or not isinstance(ip, str):
        return False
    try:
        ipaddress.ip_address(ip.strip())
        return True
    except ValueError:
        return False

def is_valid_port(port: Union[int, str]) -> bool:
    """Validate port number range and type."""
    try:
        p = int(port)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False

def resolve_hostname(hostname: str) -> Optional[str]:
    """Resolve hostname to IP address safely with error handling."""
    if not hostname:
        return None
    try:
        return socket.gethostbyname(hostname.strip())
    except (socket.gaierror, socket.herror) as e:
        logger.warning(f"Resolution failed for {hostname}: {e}")
        return None

# ----------------------------
# PUBLIC IP DETECTION
# ----------------------------

def get_public_ip() -> Optional[str]:
    """Fetch public IP using optimized fallback services."""
    import requests
    
    # Session use karne se connection reuse hota hai (fast performance)
    with requests.Session() as session:
        for url in IP_SERVICES:
            try:
                response = session.get(url, timeout=5)
                response.raise_for_status()
                ip = response.text.strip()

                if is_valid_ip(ip):
                    return ip
            except requests.RequestException as e:
                logger.debug(f"Service {url} failed: {e}")
                continue

    logger.error("All public IP services failed.")
    return None

# ----------------------------
# PARSERS (IP & TELEGRAM)
# ----------------------------

def parse_ip_port(text: str) -> Optional[Tuple[str, int]]:
    """
    Parse IP:PORT format. 
    Handles: '1.2.3.4:80', '[2001:db8::1]:8080', 'google.com:443'
    """
    if not text or ':' not in text:
        return None

    text = text.strip()
    try:
        # Handling IPv6 brackets [2001:db8::1]:80
        if text.startswith('['):
            if ']:' not in text: return None
            ip_part, port_part = text.split(']:')
            ip = ip_part.lstrip('[')
        else:
            # Handling IPv4 or hostname
            ip, port_part = text.rsplit(':', 1)

        port = int(port_part)
        
        # Validate result (allows hostname or valid IP)
        if (is_valid_ip(ip) or len(ip) > 2) and is_valid_port(port):
            return ip, port

    except (ValueError, IndexError):
        logger.debug(f"Failed to parse IP:PORT from: {text}")

    return None

def parse_telegram_invite_link(text: str) -> Optional[str]:
    """
    Extracts username or hash from any Telegram link/input.
    Handles: @username, t.me/joinchat/hash, t.me/+hash, https://t.me/user
    """
    if not text:
        return None

    text = text.strip()

    # Case 1: Simple username
    if text.startswith('@'):
        return text[1:]

    # Case 2: Regex for complex URLs
    # Pattern captures the part after t.me/ or telegram.me/
    regex = r"(?:https?:\/\/)?(?:t(?:elegram)?\.me\/|tg:\/\/join\?invite=)([^/?\s]+)"
    match = re.search(regex, text)
    
    path = match.group(1) if match else text.replace('t.me/', '')

    # Cleanup common prefixes
    if 'joinchat/' in path:
        return path.split('joinchat/')[1]
    if path.startswith('+'):
        return path
        
    return path.split('/')[0] if path else None

# ----------------------------
# FORMATTING HELPERS
# ----------------------------

def format_number(num: Union[int, float, str]) -> str:
    """Format numbers with commas (e.g., 1000 -> 1,000)"""
    try:
        return f"{int(float(num)):,}"
    except (ValueError, TypeError):
        return str(num)

def calculate_success_rate(success: int, total: int) -> float:
    """Calculate success percentage safely."""
    if not isinstance(success, int) or not isinstance(total, int) or total <= 0:
        return 0.0
    return round((success / total) * 100, 2)

def truncate_string(text: str, max_length: int = 50) -> str:
    """Truncate string with clean ellipsis handling."""
    if not text:
        return ""
    text = text.strip()
    return (text[:max_length-3] + "...") if len(text) > max_length else text
