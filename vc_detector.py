import asyncio
import logging
from typing import Optional, Tuple, Set
from dataclasses import dataclass

from pyrogram import Client, raw
from pyrogram.types import Chat
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
    """Uses USER SESSION to reliably detect active Voice Chats"""
    
    def __init__(self, user_client: Client, admin_id: int, check_interval: int = 10):
        self.user_client = user_client  # User Session (not bot)
        self.admin_id = admin_id
        self.check_interval = check_interval
        self._running = False
        self._last_detected_id = None
        self._processed_chats: Set[int] = set()

    async def _resolve_peer_safe(self, identifier: str):
        """Resolves username/ID to Peer object without cache issues"""
        try:
            # Clean identifier
            if "t.me/" in identifier:
                identifier = identifier.split("/")[-1].replace("+", "")
            if identifier.startswith("@"):
                identifier = identifier[1:]
            
            return await self.user_client.resolve_peer(identifier)
        except (PeerIdInvalid, UsernameInvalid, UsernameNotOccupied):
            logger.error(f"❌ Invalid identifier: {identifier}")
            return None
        except Exception as e:
            logger.error(f"❌ Peer Resolution Error: {e}")
            return None

    async def _fetch_vc_info(self, peer) -> Optional[VCInfo]:
        """Deep check for active call using Raw API (Guarantees accuracy)"""
        try:
            # Full chat info fetch karein (Force server sync)
            if isinstance(peer, raw.types.InputPeerChannel):
                full_chat = await self.user_client.invoke(
                    raw.functions.channels.GetFullChannel(channel=peer)
                )
            else:
                full_chat = await self.user_client.invoke(
                    raw.functions.messages.GetFullChat(chat_id=peer.chat_id)
                )

            # Check for call attribute
            call = full_chat.full_chat.call
            if call and isinstance(call, raw.types.InputGroupCall):
                # Get live participants and status
                call_data = await self.user_client.invoke(
                    raw.functions.phone.GetGroupCall(call=call, limit=1)
                )
                
                # term_date agar nahi hai, toh call active hai
                if not getattr(call_data.group_call, "term_date", None):
                    title = full_chat.chats[0].title if full_chat.chats else "Unknown"
                    username = getattr(full_chat.chats[0], "username", None)
                    
                    return VCInfo(
                        chat_id=full_chat.chats[0].id,
                        chat_title=title,
                        chat_username=username,
                        participants_count=call_data.group_call.participants_count,
                        is_active=True,
                        call_id=call.id
                    )
        except Exception as e:
            logger.debug(f"VC Check silent error: {e}")
        return None

    async def process_invite_link(self, invite_link: str) -> Optional[Tuple[int, str, VCInfo]]:
        """Used for Manual Target input"""
        try:
            logger.info(f"Processing link: {invite_link}")
            
            # Join/Get chat status
            try:
                chat = await self.user_client.join_chat(invite_link)
            except UserAlreadyParticipant:
                chat = await self.user_client.get_chat(invite_link)
            
            # 2 seconds wait for Telegram server sync
            await asyncio.sleep(2)
            
            peer = await self._resolve_peer_safe(str(chat.id))
            if not peer:
                return None
                
            vc_info = await self._fetch_vc_info(peer)
            
            # Agar VC active nahi hai toh empty container bhejein
            if not vc_info:
                vc_info = VCInfo(chat_id=chat.id, chat_title=chat.title, is_active=False)
                
            return chat.id, chat.title, vc_info

        except (InviteHashExpired, InviteHashInvalid):
            logger.error("Invite link expired or invalid.")
            return None
        except Exception as e:
            logger.error(f"Link process error: {e}")
            return None

    async def monitor_loop(self, callback):
        """Main loop to auto-detect VCs in joined groups"""
        self._running = True
        logger.info("🟢 Monitoring started via User Session...")
        
        while self._running:
            try:
                # Scan top 40 recent dialogs
                async for dialog in self.user_client.get_dialogs(limit=40):
                    if dialog.chat.type.value in ["group", "supergroup", "channel"]:
                        
                        peer = await self._resolve_peer_safe(str(dialog.chat.id))
                        if not peer:
                            continue

                        vc = await self._fetch_vc_info(peer)
                        
                        if vc and vc.is_active:
                            # Notify only if it's a new call ID
                            if self._last_detected_id != vc.call_id:
                                self._last_detected_id = vc.call_id
                                logger.info(f"🔥 VC Detected: {vc.chat_title} ({vc.participants_count} users)")
                                await callback(vc)
                                # Break to avoid flooding notifications in one cycle
                                break 
                
                await asyncio.sleep(self.check_interval)

            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.value}s")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"Monitor Loop Error: {e}")
                await asyncio.sleep(10)

    def stop(self):
        """Stop the detector"""
        self._running = False
        logger.info("🛑 Monitoring stopped.")
