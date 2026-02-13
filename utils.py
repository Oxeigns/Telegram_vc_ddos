import socket
import logging
import ipaddress
import re
import time
from typing import Optional, Tuple, Union, Dict
from scapy.all import sniff, IP, UDP

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
    try:
        ipaddress.ip_address(ip.strip())
        return True
    except ValueError:
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
# TRAFFIC ANALYZER (WIRESHARK LOGIC)
# ----------------------------

class TrafficAnalyzer:
    def __init__(self, interface: str):
        self.interface = interface
        self.captured_data = {}
        # Telegram Server Ranges
        self.tg_networks = [
            ipaddress.ip_network("149.154.160.0/20"),
            ipaddress.ip_network("91.108.0.0/16")
        ]

    def _packet_callback(self, pkt):
        if pkt.haslayer(IP) and pkt.haslayer(UDP):
            src_ip = pkt[IP].src
            # Filtering larger packets (likely Voice/Video data)
            if len(pkt[UDP]) > 100:
                self.captured_data[src_ip] = self.captured_data.get(src_ip, 0) + 1

    def start_sniffing(self, duration: int = 15):
        logger.info(f"Sniffing on {self.interface} for {duration}s... Start the VC now!")
        try:
            sniff(iface=self.interface, prn=self._packet_callback, store=0, timeout=duration)
            self.display_results()
        except Exception as e:
            logger.error(f"Error: {e}. (Make sure to run as Admin/Sudo)")

    def display_results(self):
        print("\n" + "="*50)
        print(f"{'SOURCE IP':<20} | {'PACKETS':<10} | {'TYPE'}")
        print("-"*50)
        
        sorted_ips = sorted(self.captured_data.items(), key=lambda x: x[1], reverse=True)
        
        for ip, count in sorted_ips[:10]:
            ip_obj = ipaddress.ip_address(ip)
            is_tg = any(ip_obj in net for net in self.tg_networks)
            ip_type = "TELEGRAM SERVER" if is_tg else "UNKNOWN/P2P"
            print(f"{ip:<20} | {count:<10} | {ip_type}")
        print("="*50 + "\n")

# ----------------------------
# PARSERS
# ----------------------------

def parse_telegram_invite(text: str) -> Optional[str]:
    regex = r"(?:https?:\/\/)?(?:t(?:elegram)?\.me\/|tg:\/\/join\?invite=)([^/?\s]+)"
    match = re.search(regex, text)
    return match.group(1) if match else text

# ----------------------------
# MAIN EXECUTION EXAMPLE
# ----------------------------

if __name__ == "__main__":
    # 1. Public IP Check
    print(f"Your Public IP: {get_public_ip()}")

    # 2. Traffic Analysis (Wireshark Logic)
    # Note: Replace 'Wi-Fi' with your actual interface name
    analyzer = TrafficAnalyzer(interface="Wi-Fi") 
    analyzer.start_sniffing(duration=20)
