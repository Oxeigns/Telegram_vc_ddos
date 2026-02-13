import asyncio
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from pyrogram import Client, raw
from pyrogram.types import Chat
from pyrogram.errors import (
    InviteHashExpired, InviteHashInvalid, UserAlreadyParticipant,
    FloodWait
)

logger = logging.getLogger(__name__)

@dataclass
class VCInfo:
    chat_id: int
    chat_title: str
    chat_username: Optional[str] = None
    invite_link: Optional[str] = None
    call_id: Optional[int] = None
    participants_count: int = 0
    is_active: bool = False

class VoiceChatDetector:
    def __init__(self, user_client: Client, admin_id: int, check_interval: int = 10):
        self.user_client = user_client  
        self.admin_id = admin_id
        self.check_interval = check_interval
        self._last_vc_ids = set() # Store multiple active IDs
        self._running = False

    async def _check_chat_vc(self, chat_id: int, title: str) -> Optional[VCInfo]:
        """Raw API ka use karke updated VC status check karna"""
        try:
            # Full chat info nikalna zaroori hai voice chat status ke liye
            peer = await self.user_client.resolve_peer(chat_id)
            
            if isinstance(peer, raw.types.InputPeerChannel):
                full_chat = await self.user_client.invoke(
                    raw.functions.channels.GetFullChannel(channel=peer)
                )
            else:
                full_chat = await self.user_client.invoke(
                    raw.functions.messages.GetFullChat(chat_id=peer.chat_id)
                )

            # Check if call exists and is NOT empty/closed
            call = full_chat.full_chat.call
            if call and isinstance(call, raw.types.InputGroupCall):
                # Call details fetch karna participants count ke liye
                call_details = await self.user_client.invoke(
                    raw.functions.phone.GetGroupCall(call=call, limit=1)
                )
                
                return VCInfo(
                    chat_id=chat_id,
                    chat_title=title,
                    call_id=call.id,
                    participants_count=call_details.group_call.participants_count,
                    is_active=True
                )
        except Exception as e:
            logger.debug(f"Error checking VC for {chat_id}: {e}")
        return None

    async def process_invite_link(self, invite_link: str) -> Optional[Tuple[int, str, VCInfo]]:
        """Link join karke turant VC status return karna"""
        try:
            # 1. Join Chat
            chat = await self.user_client.join_chat(invite_link)
            logger.info(f"Joined: {chat.title}")
            
            # 2. Wait 1-2 sec taaki server update ho jaye
            await asyncio.sleep(1.5)
            
            # 3. Direct check
            vc_info = await self._check_chat_vc(chat.id, chat.title)
            
            if not vc_info:
                vc_info = VCInfo(chat_id=chat.id, chat_title=chat.title, is_active=False)
            
            return (chat.id, chat.title, vc_info)
        except Exception as e:
            logger.error(f"Invite process error: {e}")
            return None

    async def check_voice_chats(self) -> Optional[VCInfo]:
        """Joined chats mein active VC dhundna"""
        try:
            # get_dialogs(limit=50) kafi hai current active chats ke liye
            async for dialog in self.user_client.get_dialogs(limit=50):
                if dialog.chat.type in [ "group", "supergroup", "channel" ]:
                    # Check if recently updated
                    vc = await self._check_chat_vc(dialog.chat.id, dialog.chat.title)
                    if vc and vc.is_active:
                        # Sirf tab return karein agar naya VC ho ya admin ko batana ho
                        if vc.chat_id not in self._last_vc_ids:
                            self._last_vc_ids.add(vc.chat_id)
                            return vc
        except Exception as e:
            logger.error(f"Monitoring check error: {e}")
        return None

    async def monitor_loop(self, callback):
        self._running = True
        logger.info("VC Monitoring Active...")
        while self._running:
            try:
                vc_info = await self.check_voice_chats()
                if vc_info:
                    await callback(vc_info)
                
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(10)

    def stop(self):
        self._running = False
