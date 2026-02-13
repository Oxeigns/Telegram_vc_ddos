import socket
import logging
import ipaddress
import re
import time
from typing import Optional, Tuple, Union, Dict

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("NetUtility")

# Constants
IP_SERVICES = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com"
]

IP_PATTERN = r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[a-fA-F0-9]{1,4}:){7}[a-fA-F0-9]{1,4}\b'

# ----------------------------
# NETWORK VALIDATION & IP TOOLS
# ----------------------------

def is_valid_ip(ip: str) -> bool:
    if not ip: return False
    try:
        ipaddress.ip_address(str(ip).strip())
        return True
    except ValueError:
        return False

def is_valid_port(port: Union[int, str]) -> bool:
    try:
        p = int(port)
        return 1 <= p <= 65535
    except:
        return False

def get_public_ip() -> Optional[str]:
    import requests
    for url in IP_SERVICES:
        try:
            response = requests.get(url, timeout=4)
            if response.status_code == 200:
                found_ips = re.findall(IP_PATTERN, response.text)
                if found_ips and is_valid_ip(found_ips[0]):
                    return found_ips[0]
        except: continue
    return None

# ----------------------------
# PARSERS (Fixes the ImportError)
# ----------------------------

def parse_ip_port(text: str) -> Optional[Tuple[str, int]]:
    """Parses 'IP:PORT' strings safely."""
    if not text or ':' not in text:
        return None
    try:
        text = text.strip()
        if text.startswith('['): # IPv6
            ip, port = text.split(']:')
            ip = ip.lstrip('[')
        else: # IPv4
            ip, port = text.rsplit(':', 1)
        
        if (is_valid_ip(ip) or len(ip) > 2) and is_valid_port(port):
            return ip, int(port)
    except:
        pass
    return None

def parse_telegram_invite_link(text: str) -> Optional[str]:
    """Matches the exact name required by bot_handler.py"""
    if not text: return None
    regex = r"(?:https?:\/\/)?(?:t(?:elegram)?\.me\/|tg:\/\/join\?invite=)([^/?\s]+)"
    match = re.search(regex, text)
    return match.group(1) if match else text.strip().replace('@', '')

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
# TRAFFIC ANALYZER (Optional/Local Only)
# ----------------------------

class TrafficAnalyzer:
    def __init__(self, interface: str):
        self.interface = interface
        self.captured_data = {}
        try:
            from scapy.all import IP, UDP
            self.has_scapy = True
        except ImportError:
            self.has_scapy = False

    def start_sniffing(self, duration: int = 15):
        if not self.has_scapy:
            logger.error("Scapy not installed. Cannot sniff.")
            return
        
        # Note: This will likely fail on Heroku but work on Local PC
        try:
            from scapy.all import sniff, IP, UDP
            def _cb(pkt):
                if pkt.haslayer(IP) and pkt.haslayer(UDP):
                    if len(pkt[UDP]) > 100:
                        self.captured_data[pkt[IP].src] = self.captured_data.get(pkt[IP].src, 0) + 1
            
            sniff(iface=self.interface, prn=_cb, store=0, timeout=duration)
        except Exception as e:
            logger.error(f"Sniffing error: {e}")

# ----------------------------
# MAIN EXECUTION
# ----------------------------

if __name__ == "__main__":
    print(f"Public IP: {get_public_ip()}")
    print(f"Parse Test: {parse_ip_port('1.1.1.1:80')}")
