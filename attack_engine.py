"""Async network diagnostics engine.

This module intentionally enforces local/private targets only to prevent abuse.
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
from dataclasses import dataclass
from typing import Optional

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
        if not self.running:
            return 0.0
        return max(0.001, time.time() - self.started_at)

    @property
    def rps(self) -> float:
        return self.sent_packets / self.elapsed


class BufferPool:
    """Reusable payload buffers for low allocation overhead."""

    def __init__(self, size: int = 1200, count: int = 512) -> None:
        self._buffers = [os.urandom(size) for _ in range(count)]
        self._idx = 0

    def next(self) -> bytes:
        payload = self._buffers[self._idx]
        self._idx = (self._idx + 1) % len(self._buffers)
        return payload


class AttackEngine:
    """High-concurrency diagnostics for user-owned systems."""

    def __init__(self, max_threads: int, max_duration: int) -> None:
        self.max_threads = max_threads
        self.max_duration = max_duration
        self.stats = AttackStats()
        self._stop_event = asyncio.Event()
        self._workers: list[asyncio.Task] = []
        self._buffer_pool = BufferPool()

    def stop(self) -> None:
        self._stop_event.set()

    async def run_udp_test(self, ip: str, port: int, duration: int) -> AttackStats:
        if not is_private_or_loopback(ip):
            raise ValueError("Safety block: diagnostics are allowed only for local/private targets")

        run_seconds = min(duration, self.max_duration)
        worker_count = self.max_threads

        self.stats = AttackStats(started_at=time.time(), running=True)
        self._stop_event.clear()

        loop = asyncio.get_running_loop()
        for _ in range(worker_count):
            task = asyncio.create_task(self._udp_worker(loop, ip, port))
            self._workers.append(task)

        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=run_seconds)
        except asyncio.TimeoutError:
            pass
        finally:
            self._stop_event.set()
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()
            self.stats.running = False

        return self.stats

    async def _udp_worker(self, loop: asyncio.AbstractEventLoop, ip: str, port: int) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)

        try:
            while not self._stop_event.is_set():
                payload = self._buffer_pool.next()
                ok = await loop.run_in_executor(None, self._sendto, sock, payload, ip, port)
                if ok:
                    self.stats.sent_packets += 1
                    self.stats.bytes_sent += len(payload)
                else:
                    self.stats.failed_packets += 1
        finally:
            sock.close()

    @staticmethod
    def _sendto(sock: socket.socket, payload: bytes, ip: str, port: int) -> bool:
        try:
            sock.sendto(payload, (ip, port))
            return True
        except OSError:
            return False

    async def run_tcp_probe(self, ip: str, port: int, attempts: int = 25) -> dict:
        if not is_private_or_loopback(ip):
            raise ValueError("Safety block: TCP probe is allowed only for local/private targets")

        success = 0
        for _ in range(attempts):
            sock: Optional[socket.socket] = None
            try:
                sock = socket.create_connection((ip, port), timeout=2)
                success += 1
            except OSError:
                pass
            finally:
                if sock:
                    sock.close()
        return {"attempts": attempts, "success": success, "failed": attempts - success}
