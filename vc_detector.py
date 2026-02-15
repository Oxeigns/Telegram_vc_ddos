"""Enhanced On-demand Telegram voice chat detector with proper IP extraction."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Optional, List, Dict

from pyrogram import Client
from pyrogram.errors import ChatAdminRequired, FloodWait, UserAlreadyParticipant
from pyrogram.raw import functions, types

LOGGER = logging.getLogger(__name__)


@dataclass
class VCRecord:
    dialog_id: int
    title: str
    peer: Any
    call: Any
    chat_id: int


@dataclass  
class VCConnectionInfo:
    """Structured VC connection information."""
    ip: str
    port: int
    type: str  # 'udp', 'tcp', etc.
    region: str
    raw_endpoint: str


class VCDetector:
    def __init__(self, user_client: Client, scan_cooldown_seconds: int = 10) -> None:
        self.user_client = user_client
        self.scan_cooldown_seconds = scan_cooldown_seconds
        self._last_scan = 0.0

    async def scan_active_voice_chats(self, limit: int = 50) -> list[VCRecord]:
        now = time.time()
        if now - self._last_scan < self.scan_cooldown_seconds:
            await asyncio.sleep(self.scan_cooldown_seconds - (now - self._last_scan))

        self._last_scan = time.time()
        results: list[VCRecord] = []

        async for dialog in self.user_client.get_dialogs(limit=limit):
            chat = dialog.chat
            try:
                peer = await self.user_client.resolve_peer(chat.id)
                call = await self._extract_call(peer)
                if call:
                    results.append(VCRecord(
                        dialog_id=chat.id, 
                        title=chat.title or str(chat.id), 
                        peer=peer, 
                        call=call,
                        chat_id=chat.id
                    ))
            except FloodWait as wait_err:
                LOGGER.warning("FloodWait during scan: %s", wait_err.value)
                raise
            except Exception as exc:
                LOGGER.debug("Skipping dialog %s: %s", chat.id, exc)

        return results

    async def _extract_call(self, peer: Any) -> Optional[Any]:
        if isinstance(peer, types.InputPeerChannel):
            full = await self.user_client.invoke(
                functions.channels.GetFullChannel(channel=types.InputChannel(channel_id=peer.channel_id, access_hash=peer.access_hash))
            )
            return getattr(full.full_chat, "call", None)

        if isinstance(peer, types.InputPeerChat):
            full = await self.user_client.invoke(functions.messages.GetFullChat(chat_id=peer.chat_id))
            return getattr(full.full_chat, "call", None)

        return None

    async def join_and_extract_metadata(self, record: VCRecord) -> dict:
        """Join active VC and fetch complete metadata including IP addresses."""
        joined = False
        notice: Optional[str] = None

        try:
            await self.user_client.invoke(
                functions.phone.JoinGroupCall(
                    call=types.InputGroupCall(id=record.call.id, access_hash=record.call.access_hash),
                    join_as=record.peer,
                    params=types.DataJSON(data=json.dumps({
                        "ufrag": "vc_detector",
                        "pwd": "vc_test_123",
                        "fingerprints": [],
                        "ssrc": 11111111
                    })),
                    muted=True,
                    video_stopped=True,
                    invite_hash=None,
                )
            )
            joined = True
            LOGGER.info("Joined active VC in %s", record.title)
            await asyncio.sleep(2)  # Wait for connection establishment
        except UserAlreadyParticipant:
            joined = True
            LOGGER.info("Already joined in %s", record.title)
        except ChatAdminRequired as exc:
            notice = "Join blocked by Telegram admin restriction; fetched metadata without joining."
            LOGGER.warning("Admin restriction in %s: %s", record.title, exc)
        except Exception as exc:
            LOGGER.warning("Join attempt failed: %s", exc)
            notice = f"Join failed: {exc}"

        # Fetch detailed group call info
        group_call = await self.user_client.invoke(
            functions.phone.GetGroupCall(
                call=types.InputGroupCall(id=record.call.id, access_hash=record.call.access_hash),
                limit=100,
            )
        )

        call = group_call.call
        params_raw = getattr(call, "params", None)
        params_data = getattr(params_raw, "data", "{}") if params_raw else "{}"

        try:
            parsed = json.loads(params_data)
        except json.JSONDecodeError:
            parsed = {"raw": params_data}

        # Extract IP addresses from multiple sources
        extracted_ips = []
        
        # Source 1: endpoints in params
        candidates = parsed.get("endpoints", []) if isinstance(parsed, dict) else []
        for endpoint in candidates:
            ip_info = self._parse_endpoint(endpoint)
            if ip_info:
                extracted_ips.append(ip_info)

        # Source 2: connection description
        if isinstance(parsed, dict):
            # Look for any IP patterns in the entire params
            params_str = json.dumps(parsed)
            ip_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
            found_ips = re.findall(ip_pattern, params_str)
            for ip in found_ips:
                if ip not in [x.ip for x in extracted_ips]:
                    extracted_ips.append(VCConnectionInfo(
                        ip=ip, port=0, type="unknown", region="unknown", raw_endpoint=ip
                    ))

        # Source 3: participants info (if available)
        participants = getattr(group_call, "participants", [])
        for participant in participants:
            try:
                peer_ip = getattr(participant, "ip", None)
                if peer_ip and peer_ip not in [x.ip for x in extracted_ips]:
                    extracted_ips.append(VCConnectionInfo(
                        ip=str(peer_ip), port=0, type="participant", region="unknown", raw_endpoint=str(peer_ip)
                    ))
            except:
                pass

        # Resolve hostnames if present
        final_ips = []
        for ip_info in extracted_ips:
            if ip_info.ip and not self._is_valid_ip(ip_info.ip):
                # Try to resolve hostname
                try:
                    resolved = socket.gethostbyname(ip_info.ip)
                    if resolved:
                        final_ips.append(VCConnectionInfo(
                            ip=resolved,
                            port=ip_info.port,
                            type=ip_info.type,
                            region=ip_info.region,
                            raw_endpoint=ip_info.raw_endpoint
                        ))
                except:
                    pass
            else:
                final_ips.append(ip_info)

        return {
            "title": record.title,
            "call_id": record.call.id,
            "chat_id": record.chat_id,
            "params": parsed,
            "endpoint_candidates": candidates,
            "extracted_ips": [
                {
                    "ip": x.ip,
                    "port": x.port,
                    "type": x.type,
                    "region": x.region
                } for x in final_ips
            ],
            "joined": joined,
            "notice": notice,
            "participants_count": len(participants) if participants else 0,
        }

    def _parse_endpoint(self, endpoint: str) -> Optional[VCConnectionInfo]:
        """Parse endpoint string to extract IP and port."""
        if not endpoint:
            return None

        # Pattern 1: IP:PORT
        if ":" in endpoint:
            parts = endpoint.rsplit(":", 1)
            if len(parts) == 2:
                ip, port_str = parts
                try:
                    port = int(port_str)
                    if self._is_valid_ip(ip):
                        return VCConnectionInfo(ip=ip, port=port, type="direct", region="auto", raw_endpoint=endpoint)
                except:
                    pass

        # Pattern 2: hostname:port
        try:
            if ":" in endpoint:
                hostname, port_str = endpoint.rsplit(":", 1)
                port = int(port_str)
                return VCConnectionInfo(ip=hostname, port=port, type="hostname", region="unknown", raw_endpoint=endpoint)
        except:
            pass

        # Pattern 3: Just IP
        if self._is_valid_ip(endpoint):
            return VCConnectionInfo(ip=endpoint, port=0, type="ip_only", region="unknown", raw_endpoint=endpoint)

        return None

    def _is_valid_ip(self, ip: str) -> bool:
        """Check if string is valid IP address."""
        try:
            socket.inet_aton(ip)
            return True
        except socket.error:
            return False

    async def leave_call(self, record: VCRecord) -> None:
        try:
            await self.user_client.invoke(
                functions.phone.LeaveGroupCall(
                    call=types.InputGroupCall(id=record.call.id, access_hash=record.call.access_hash), 
                    source=0
                )
            )
            LOGGER.info("Left VC in %s", record.title)
        except Exception as exc:
            LOGGER.warning("Error leaving call: %s", exc)
