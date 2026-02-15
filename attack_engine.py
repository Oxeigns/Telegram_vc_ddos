"""
Async Network Diagnostics Engine (Optimized)
Enforces local/private targets only.
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
from dataclasses import dataclass
from typing import Optional

# Maan ke chal rahe hain ki utils.py me ye function maujood hai
from utils import is_private_or_loopback


@dataclass
class AttackStats:
    sent_packets: int = 0
    failed_packets: int = 0
    bytes_sent: int = 0
    started_at: float = 0.0
    running: bool = False

    @property
    def elapsed(self) -> float:
        if not self.running or self.started_at == 0:
            return 0.001
        return max(0.001, time.time() - self.started_at)

    @property
    def rps(self) -> float:
        return self.sent_packets / self.elapsed


class BufferPool:
    """Low-overhead payload management."""
    def __init__(self, size: int = 1200, count: int = 512) -> None:
        self._buffers = [os.urandom(size) for _ in range(count)]
        self._idx = 0

    def next(self) -> bytes:
        payload = self._buffers[self._idx]
        self._idx = (self._idx + 1) % len(self._buffers)
        return payload


class AttackEngine:
    """High-performance diagnostics for private network systems."""

    def __init__(self, max_threads: int, max_duration: int) -> None:
        self.max_threads = max_threads
        self.max_duration = max_duration
        self.stats = AttackStats()
        self._stop_event = asyncio.Event()
        self._workers: list[asyncio.Task] = []
        self._buffer_pool = BufferPool()

    async def run_udp_test(self, ip: str, port: int, duration: int) -> AttackStats:
        if not is_private_or_loopback(ip):
            raise ValueError("Safety block: Local/Private targets only.")

        run_seconds = min(duration, self.max_duration)
        self.stats = AttackStats(started_at=time.time(), running=True)
        self._stop_event.clear()

        # UDP Socket Setup (Non-blocking)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)

        # Workers creation
        for _ in range(self.max_threads):
            task = asyncio.create_task(self._udp_worker(sock, ip, port))
            self._workers.append(task)

        try:
            # Wait for the specified duration
            await asyncio.sleep(run_seconds)
        finally:
            self._stop_event.set()
            # Stop all workers and cleanup
            for task in self._workers:
                task.cancel()
            
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()
            sock.close()
            self.stats.running = False

        return self.stats

    async def _udp_worker(self, sock: socket.socket, ip: str, port: int) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop_event.is_set():
            payload = self._buffer_pool.next()
            try:
                # Direct non-blocking send
                sock.sendto(payload, (ip, port))
                self.stats.sent_packets += 1
                self.stats.bytes_sent += len(payload)
            except BlockingIOError:
                # Buffer full, wait a tiny bit for the next event loop tick
                await asyncio.sleep(0)
            except OSError:
                self.stats.failed_packets += 1
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break

    async def run_tcp_probe(self, ip: str, port: int, attempts: int = 25) -> dict:
        """Native async TCP connection testing."""
        if not is_private_or_loopback(ip):
            raise ValueError("Safety block: Local/Private targets only.")

        success = 0
        for _ in range(attempts):
            try:
                # asyncio.open_connection is much faster and non-blocking
                conn = asyncio.open_connection(ip, port)
                reader, writer = await asyncio.wait_for(conn, timeout=1.5)
                success += 1
                writer.close()
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError):
                continue
        
        return {
            "target": f"{ip}:{port}",
            "attempts": attempts, 
            "success": success, 
            "failed": attempts - success
        }
