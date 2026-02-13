import socket

def is_valid_ip(ip: str) -> bool:
    """Validate IPv4 aur IPv6 dono ke liye"""
    if not ip:
        return False
    
    # Pehle IPv4 check karein
    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except socket.error:
        pass
    
    # Phir IPv6 check karein
    try:
        socket.inet_pton(socket.AF_INET6, ip)
        return True
    except socket.error:
        return False

def parse_ip_port(text: str):
    """Parse IP:PORT format (IPv4 aur IPv6 handling ke sath)"""
    if not text:
        return None
    
    try:
        # IPv6 mein aksar multiple colon hote hain, 
        # isliye rsplit(':', 1) use karna sahi hai taaki sirf aakhri colon port mana jaye
        parts = text.rsplit(':', 1)
        if len(parts) != 2:
            return None
            
        ip = parts[0].strip("[]") # IPv6 brackets [2001:db8::1] ko handle karne ke liye
        port_str = parts[1]
        
        if not port_str.isdigit():
            return None
            
        port = int(port_str)
        
        if is_valid_ip(ip) and 1 <= port <= 65535:
            return ip, port
    except (ValueError, IndexError):
        pass
    return None

def format_number(num) -> str:
    """Numbers ko 1,234,567 format mein dikhane ke liye"""
    try:
        # Check agar number valid hai
        return "{:,}".format(int(num))
    except (ValueError, TypeError):
        return "0"
