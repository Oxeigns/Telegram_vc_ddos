"""
Utility functions for network operations and validation
"""

import socket
import random
import string
import logging
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def is_valid_ip(ip: str) -> bool:
    """Validate IPv4 address"""
    if not ip or not isinstance(ip, str):
        return False
    try:
        socket.inet_aton(ip)
        return True
    except socket.error:
        return False


def is_valid_port(port: int) -> bool:
    """Validate port number"""
    return isinstance(port, int) and 1 <= port <= 65535


def resolve_hostname(hostname: str) -> Optional[str]:
    """Resolve hostname to IP address"""
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror as e:
        logger.error(f"Failed to resolve {hostname}: {e}")
        return None


def generate_random_subdomain(length: int = 12) -> str:
    """Generate random subdomain for DNS queries"""
    return ''.join(random.choices(string.ascii_lowercase, k=length))


def get_public_ip() -> str:
    """Get server's public IP address"""
    try:
        import requests
        response = requests.get('https://api.ipify.org', timeout=5)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Failed to get public IP: {e}")
        return "127.0.0.1"


def parse_ip_port(text: str) -> Optional[Tuple[str, int]]:
    """Parse IP:PORT format"""
    if not text or ':' not in text:
        return None
    
    try:
        # Handle IPv6 addresses in brackets
        if text.startswith('['):
            ip, port_str = text.rsplit(':', 1)
            ip = ip[1:-1]
            port = int(port_str)
        else:
            ip, port_str = text.rsplit(':', 1)
            port = int(port_str)
        
        if is_valid_ip(ip) and is_valid_port(port):
            return ip, port
    except (ValueError, IndexError):
        pass
    return None


def parse_telegram_invite_link(link: str) -> Optional[str]:
    """
    Parse Telegram invite link to extract chat identifier
    Supports:
    - https://t.me/+AbCdEfGhIjK (invite links)
    - https://t.me/groupname (public groups)
    - t.me/+AbCdEfGhIjK
    - t.me/groupname
    - @groupname
    """
    if not link:
        return None
    
    link = link.strip()
    
    # Handle @username format
    if link.startswith('@'):
        return link[1:]
    
    # Remove protocol and www
    if '://' in link:
        parsed = urlparse(link)
        path = parsed.path.strip('/')
    else:
        path = link.replace('t.me/', '').strip('/')
    
    # Extract chat identifier
    if path.startswith('+'):
        # Private invite link hash
        return path
    elif path:
        # Public group/channel username
        return path
    
    return None


def format_number(num: int) -> str:
    """Format large numbers with commas"""
    try:
        return f"{int(num):,}"
    except (ValueError, TypeError):
        return str(num)


def calculate_success_rate(success: int, total: int) -> float:
    """Calculate success percentage"""
    if total == 0:
        return 0.0
    return (success / total) * 100


def truncate_string(text: str, max_length: int = 50) -> str:
    """Truncate string with ellipsis"""
    if not text:
        return ""
    if len(text) > max_length:
        return text[:max_length-3] + "..."
    return text
