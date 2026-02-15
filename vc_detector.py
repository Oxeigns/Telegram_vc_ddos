"""On-demand Telegram voice chat detector using raw API methods."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

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
                    results.append(VCRecord(dialog_id=chat.id, title=chat.title or str(chat.id), peer=peer, call=call))
            except FloodWait as wait_err:
                LOGGER.warning("FloodWait during scan: %s", wait_err.value)
                raise
            except Exception as exc:  # best-effort scan
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
        """Join active VC when possible, then fetch transport metadata."""
        joined = False
        notice: Optional[str] = None

        try:
            await self.user_client.invoke(
                functions.phone.JoinGroupCall(
                    call=types.InputGroupCall(id=record.call.id, access_hash=record.call.access_hash),
                    join_as=record.peer,
                    params=types.DataJSON(data=json.dumps({"ufrag": "", "pwd": ""})),
                    muted=True,
                    video_stopped=True,
                    invite_hash=None,
                )
            )
            joined = True
            LOGGER.info("Joined active VC in %s", record.title)
        except UserAlreadyParticipant:
            joined = True
            LOGGER.info("Already joined in %s", record.title)
        except ChatAdminRequired as exc:
            notice = "Join blocked by Telegram admin restriction; fetched VC metadata without joining."
            LOGGER.warning("Join blocked by admin requirement in %s: %s", record.title, exc)

        group_call = await self.user_client.invoke(
            functions.phone.GetGroupCall(
                call=types.InputGroupCall(id=record.call.id, access_hash=record.call.access_hash),
                limit=1,
            )
        )

        call = group_call.call
        params_raw = getattr(call, "params", None)
        params_data = getattr(params_raw, "data", "{}") if params_raw else "{}"

        try:
            parsed = json.loads(params_data)
        except json.JSONDecodeError:
            parsed = {"raw": params_data}

        candidates = parsed.get("endpoints", []) if isinstance(parsed, dict) else []
        return {
            "title": record.title,
            "call_id": record.call.id,
            "params": parsed,
            "endpoint_candidates": candidates,
            "joined": joined,
            "notice": notice,
        }

    async def leave_call(self, record: VCRecord) -> None:
        await self.user_client.invoke(
            functions.phone.LeaveGroupCall(call=types.InputGroupCall(id=record.call.id, access_hash=record.call.access_hash), source=0)
        )
