import asyncio
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

from pyrogram import Client, raw
from pyrogram.errors import (
    UserAlreadyParticipant,
    FloodWait
)

logger = logging.getLogger(__name__)


@dataclass
class VCInfo:
    chat_id: int
    chat_title: str
    participants_count: int = 0
    is_active: bool = False
    call_id: Optional[int] = None
    chat_username: Optional[str] = None


class VoiceChatDetector:

    def __init__(self, user_client: Client, admin_id: int, check_interval: int = 15):
        self.user_client = user_client
        self.admin_id = admin_id
        self.check_interval = check_interval
        self._running = False
        self._last_detected_id = None

    # -------------------------
    # SAFE VC FETCH
    # -------------------------

    async def _fetch_vc_info(self, chat_id: int) -> Optional[VCInfo]:
        try:
            peer = await self.user_client.resolve_peer(chat_id)

            # CHANNEL / SUPERGROUP
            if isinstance(peer, raw.types.InputPeerChannel):
                full_chat = await self.user_client.invoke(
                    raw.functions.channels.GetFullChannel(channel=peer)
                )
                chat_obj = full_chat.chats[0]
                full = full_chat.full_chat
            else:
                full_chat = await self.user_client.invoke(
                    raw.functions.messages.GetFullChat(chat_id=chat_id)
                )
                chat_obj = full_chat.chats[0]
                full = full_chat.full_chat

            # No active call
            if not getattr(full, "call", None):
                return None

            call = full.call

            # 🔥 FIX HERE
            call_data = await self.user_client.invoke(
                raw.functions.phone.GetGroupCall(
                    call=call,
                    limit=1
                )
            )

            # call_data itself IS GroupCall
            if not getattr(call_data, "term_date", None):

                return VCInfo(
                    chat_id=chat_obj.id,
                    chat_title=chat_obj.title,
                    chat_username=getattr(chat_obj, "username", None),
                    participants_count=getattr(call_data, "participants_count", 0),
                    is_active=True,
                    call_id=call.id
                )

        except Exception as e:
            logger.error(f"VC fetch error: {e}")

        return None

    # -------------------------
    # MANUAL INVITE CHECK
    # -------------------------

    async def process_invite_link(self, invite_link: str) -> Optional[Tuple[int, str, VCInfo]]:
        try:
            try:
                chat = await self.user_client.join_chat(invite_link)
            except UserAlreadyParticipant:
                chat = await self.user_client.get_chat(invite_link)

            await asyncio.sleep(2)

            vc_info = await self._fetch_vc_info(chat.id)

            if not vc_info:
                vc_info = VCInfo(
                    chat_id=chat.id,
                    chat_title=chat.title,
                    is_active=False
                )

            return chat.id, chat.title, vc_info

        except Exception as e:
            logger.error(f"Manual process error: {e}")
            return None

    # -------------------------
    # AUTO MONITOR LOOP
    # -------------------------

    async def monitor_loop(self, callback):
        self._running = True
        logger.info("🟢 VC Auto Detection Started")

        while self._running:
            try:
                async for dialog in self.user_client.get_dialogs(limit=30):

                    if not self._running:
                        break

                    if dialog.chat.type.value in ["group", "supergroup", "channel"]:

                        vc = await self._fetch_vc_info(dialog.chat.id)

                        if vc and vc.is_active:

                            if self._last_detected_id != vc.call_id:
                                self._last_detected_id = vc.call_id
                                logger.info(f"🔥 VC Detected: {vc.chat_title}")
                                await callback(vc)
                                break

                await asyncio.sleep(self.check_interval)

            except FloodWait as e:
                await asyncio.sleep(e.value)

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(10)

    def stop(self):
        self._running = False
