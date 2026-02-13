import asyncio
import logging
from typing import Optional, Tuple, Set
from dataclasses import dataclass

from pyrogram import Client, raw
from pyrogram.errors import (
    InviteHashExpired, InviteHashInvalid, UserAlreadyParticipant,
    FloodWait, PeerIdInvalid, UsernameInvalid, UsernameNotOccupied
)

logger = logging.getLogger(__name__)

@dataclass
class VCInfo:
    """Voice Chat details container"""
    chat_id: int
    chat_title: str
    participants_count: int = 0
    is_active: bool = False
    call_id: Optional[int] = None
    chat_username: Optional[str] = None

class VoiceChatDetector:
    """Uses USER SESSION to detect VCs (Auto-scan + Manual link)"""
    
    def __init__(self, user_client: Client, admin_id: int, check_interval: int = 15):
        self.user_client = user_client 
        self.admin_id = admin_id
        self.check_interval = check_interval
        self._running = False
        self._last_detected_id = None # Duplicate notifications rokne ke liye

    def _parse_identifier(self, text: str) -> str:
        """Link se username nikaalne ke liye logic (Fixes USERNAME_INVALID)"""
        text = text.strip()
        if "t.me/" in text or "telegram.me/" in text:
            # https://t.me/paidmodchatowns -> paidmodchatowns
            identifier = text.split('/')[-1].replace('@', '').split('?')[0]
            return identifier
        if text.startswith('@'):
            return text[1:]
        return text

    async def _get_peer_reliable(self, identifier: str):
        """Username ya ID ko Peer object mein badalta hai safely"""
        try:
            parsed_id = self._parse_identifier(identifier)
            # Agar ID hai toh integer mein convert karein
            if parsed_id.startswith(("-100", "-1")) or parsed_id.isdigit():
                return await self.user_client.resolve_peer(int(parsed_id))
            # Username ke liye
            return await self.user_client.resolve_peer(parsed_id)
        except Exception as e:
            logger.error(f"❌ Peer Resolution Failed: {e}")
            return None

    async def _fetch_vc_info(self, peer) -> Optional[VCInfo]:
        """Raw API se VC ki live information nikaalta hai"""
        try:
            if isinstance(peer, raw.types.InputPeerChannel):
                full_chat = await self.user_client.invoke(
                    raw.functions.channels.GetFullChannel(channel=peer)
                )
            else:
                full_chat = await self.user_client.invoke(
                    raw.functions.messages.GetFullChat(chat_id=peer.chat_id)
                )

            call = full_chat.full_chat.call
            if call and isinstance(call, raw.types.InputGroupCall):
                call_data = await self.user_client.invoke(
                    raw.functions.phone.GetGroupCall(call=call, limit=1)
                )
                
                # term_date nahi hai matlab call active hai
                if not getattr(call_data.group_call, "term_date", None):
                    return VCInfo(
                        chat_id=full_chat.chats[0].id,
                        chat_title=full_chat.chats[0].title,
                        chat_username=getattr(full_chat.chats[0], "username", None),
                        participants_count=call_data.group_call.participants_count,
                        is_active=True,
                        call_id=call.id
                    )
        except Exception:
            pass
        return None

    # --- MANUAL DETECTION ---
    async def process_invite_link(self, invite_link: str) -> Optional[Tuple[int, str, VCInfo]]:
        """Manual target ke liye: Pehle join karega phir check karega"""
        try:
            logger.info(f"🔍 Manual Check: {invite_link}")
            
            # Link clean karein
            identifier = self._parse_identifier(invite_link)
            
            try:
                chat = await self.user_client.join_chat(invite_link)
            except UserAlreadyParticipant:
                chat = await self.user_client.get_chat(identifier)
            except Exception as e:
                logger.error(f"Join Error: {e}")
                return None

            await asyncio.sleep(2) # Sync delay
            peer = await self._get_peer_reliable(str(chat.id))
            vc_info = await self._fetch_vc_info(peer) if peer else None
            
            if not vc_info:
                vc_info = VCInfo(chat_id=chat.id, chat_title=chat.title, is_active=False)

            return chat.id, chat.title, vc_info
        except Exception as e:
            logger.error(f"❌ Manual Process Error: {e}")
            return None

    # --- AUTO DETECTION ---
    async def monitor_loop(self, callback):
        """Continuous Loop: Joined groups ko scan karke auto-detect karega"""
        self._running = True
        logger.info("🟢 Auto-Detection Started (User Session Mode)")
        
        while self._running:
            try:
                # Top 30 active groups ko check karein
                async for dialog in self.user_client.get_dialogs(limit=30):
                    if not self._running: break
                    
                    if dialog.chat.type.value in ["group", "supergroup", "channel"]:
                        peer = await self._get_peer_reliable(str(dialog.chat.id))
                        if not peer: continue

                        vc = await self._fetch_vc_info(peer)
                        
                        if vc and vc.is_active:
                            # Nayi call milne par notify karein
                            if self._last_detected_id != vc.call_id:
                                self._last_detected_id = vc.call_id
                                logger.info(f"🔥 Auto-Detected: {vc.chat_title}")
                                await callback(vc)
                                # Ek cycle mein ek hi notification (Flood prevent)
                                break 
                
                # Check interval ke hisaab se wait karein
                await asyncio.sleep(self.check_interval)

            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"Monitor Loop Error: {e}")
                await asyncio.sleep(10)

    def stop(self):
        self._running = False
