"""
Utility Functions - Network Tools & Validators
"""

import socket
import logging
import ipaddress
import re
from typing import Optional, Tuple, Union

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Utils")


def is_valid_ip(ip: str) -> bool:
    """Validate IPv4/IPv6 address"""
    if not ip or not isinstance(ip, str):
        return False
    try:
        ipaddress.ip_address(ip.strip())
        return True
    except ValueError:
        return False


def is_valid_port(port: Union[int, str]) -> bool:
    """Validate port number (1-65535)"""
    try:
        p = int(port)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False


def get_public_ip() -> Optional[str]:
    """Get public IP using multiple services"""
    services = [
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://icanhazip.com"
    ]
    
    for url in services:
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=5) as response:
                ip = response.read().decode().strip()
                if is_valid_ip(ip):
                    return ip
        except Exception as e:
            logger.debug(f"Failed to get IP from {url}: {e}")
            continue
    
    return None


def parse_ip_port(text: str) -> Optional[Tuple[str, int]]:
    """Parse IP:PORT format - supports IPv4 and IPv6"""
    if not text or ':' not in text:
        return None
    
    text = text.strip()
    
    try:
        # IPv6 format: [::1]:80 or [2001:db8::1]:443
        if text.startswith('['):
            bracket_end = text.find(']')
            if bracket_end == -1:
                return None
            
            ip = text[1:bracket_end]
            port_part = text[bracket_end + 1:]
            
            if port_part.startswith(':'):
                port = int(port_part[1:])
            else:
                return None
        else:
            # IPv4 format: 192.168.1.1:80
            # Handle multiple colons (IPv4 with port)
            if text.count(':') == 1:
                ip, port_str = text.split(':')
                port = int(port_str)
            else:
                # Might be IPv6 without brackets - invalid format
                return None
        
        # Validate
        if is_valid_ip(ip) and is_valid_port(port):
            return ip, port
            
    except (ValueError, IndexError) as e:
        logger.debug(f"Parse error: {e}")
    
    return None


def parse_telegram_invite_link(text: str) -> Optional[str]:
    """Extract chat identifier from Telegram links"""
    if not text:
        return None
    
    text = text.strip()
    
    # @username format
    if text.startswith('@'):
        return text[1:]
    
    # Regex for various Telegram link formats
    patterns = [
        r't\.me/\+([^/?\s]+)',      # t.me/+AbCdEf
        r't\.me/joinchat/([^/?\s]+)', # t.me/joinchat/AbCdEf
        r't\.me/([^/?\s]+)',         # t.me/groupname
        r'telegram\.me/([^/?\s]+)',  # telegram.me/groupname
        r'tg://join\?invite=([^\s]+)' # tg://join?invite=AbCdEf
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    
    # If no pattern matched, return as-is (might be direct username)
    return text if len(text) > 2 else None


def format_number(num: Union[int, float, str]) -> str:
    """Format number with commas"""
    try:
        return f"{int(float(num)):,}"
    except (ValueError, TypeError):
        return str(num)


def calculate_success_rate(success: int, total: int) -> float:
    """Calculate success percentage"""
    if not total or total <= 0:
        return 0.0
    return round((success / total) * 100, 2)


def truncate_string(text: str, max_length: int = 50) -> str:
    """Truncate string with ellipsis"""
    if not text:
        return ""
    if len(text) > max_length:
        return text[:max_length-3] + "..."
    return text


def resolve_hostname(hostname: str) -> Optional[str]:
    """Resolve hostname to IP"""
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror as e:
        logger.error(f"Failed to resolve {hostname}: {e}")
        return None


# Test if run directly
if __name__ == "__main__":
    print("✅ Utils loaded successfully")
    
    # Test cases
    print(f"IPv4 valid: {is_valid_ip('192.168.1.1')}")
    print(f"IPv6 valid: {is_valid_ip('::1')}")
    print(f"Parse IP:PORT: {parse_ip_port('192.168.1.1:8080')}")
    print(f"Format number: {format_number(1234567)}")
