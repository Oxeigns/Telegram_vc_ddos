"""
Utility Functions
"""

import socket


def is_valid_ip(ip: str) -> bool:
    """Validate IPv4"""
    if not ip:
        return False
    try:
        socket.inet_aton(ip)
        return True
    except socket.error:
        return False


def parse_ip_port(text: str):
    """Parse IP:PORT format"""
    if not text or ':' not in text:
        return None
    try:
        ip, port_str = text.rsplit(':', 1)
        port = int(port_str)
        if is_valid_ip(ip) and 1 <= port <= 65535:
            return ip, port
    except (ValueError, IndexError):
        pass
    return None


def format_number(num) -> str:
    """Format with commas"""
    try:
        return f"{int(num):,}"
    except (ValueError, TypeError):
        return str(num)
