"""
Voice Chat Detection Module
Uses USER SESSION (not bot) to join groups and detect VCs
"""

import asyncio
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from pyrogram import Client
from pyrogram.types import Chat
from pyrogram.errors import (
    InviteHashExpired, InviteHashInvalid, UserAlreadyParticipant,
    ChannelInvalid, ChannelPrivate, FloodWait, PeerIdInvalid
)

logger = logging.getLogger(__name__)


@dataclass
class VCInfo:
    """Voice Chat information container"""
    chat_id: int
    chat_title: str
    chat_username: Optional[str] = None
    invite_link: Optional[str] = None
    call_id: Optional[int] = None
    participants_count: int = 0
    is_active: bool = False
    server_ip: Optional[str] = None


class VoiceChatDetector:
    """Uses USER CLIENT to detect VCs and process invite links"""
    
    def __init__(self, user_client: Client, admin_id: int, check_interval: int = 10):
        self.user_client = user_client  # USER SESSION - not bot!
        self.admin_id = admin_id
        self.check_interval = check_interval
        self._last_vc: Optional[VCInfo] = None
        self._running = False
        self._processed_links = set()  # Cache to avoid reprocessing
    
    async def process_invite_link(self, invite_link: str) -> Optional[Tuple[int, str, VCInfo]]:
        """
        Process invite link using USER CLIENT
        Returns: (chat_id, chat_title, vc_info) or None
        """
        try:
            logger.info(f"[USER CLIENT] Processing invite link: {invite_link}")
            
            # Clean and parse the link
            link = invite_link.strip()
            
            # Extract identifier from various formats
            chat_identifier = None
            
            if 't.me/+' in link or 'telegram.me/+' in link:
                # Private invite: t.me/+AbCdEfGhIjK
                chat_identifier = '+' + link.split('/+')[-1].split('/')[0].split('?')[0]
            elif 'joinchat' in link:
                # Old format: t.me/joinchat/AbCdEfGhIjK
                chat_identifier = link.split('joinchat/')[-1].split('/')[0].split('?')[0]
            elif 't.me/' in link or 'telegram.me/' in link:
                # Public group: t.me/groupname
                parts = link.split('t.me/')[-1].split('/')
                chat_identifier = parts[0].split('?')[0]
            elif link.startswith('@'):
                # @username format
                chat_identifier = link[1:]
            else:
                # Assume it's a username or hash directly
                chat_identifier = link
            
            if not chat_identifier:
                logger.error("Could not extract chat identifier")
                return None
            
            logger.info(f"[USER CLIENT] Extracted identifier: {chat_identifier}")
            
            # Try to join/get chat using USER CLIENT (not bot!)
            chat = None
            
            try:
                if chat_identifier.startswith('+'):
                    # Private invite link - join using the link
                    full_link = f"https://t.me/{chat_identifier}"
                    logger.info(f"[USER CLIENT] Joining private chat: {full_link}")
                    chat = await self.user_client.join_chat(full_link)
                else:
                    # Public group or username
                    logger.info(f"[USER CLIENT] Joining public chat: {chat_identifier}")
                    chat = await self.user_client.join_chat(chat_identifier)
                
                logger.info(f"[USER CLIENT] Successfully joined: {chat.title} (ID: {chat.id})")
                
            except UserAlreadyParticipant:
                logger.info("[USER CLIENT] Already in chat, getting info...")
                try:
                    # Get chat info - try different methods
                    if chat_identifier.startswith('+'):
                        # For private chats, search in dialogs
                        async for dialog in self.user_client.get_dialogs(limit=200):
                            if dialog.chat and hasattr(dialog.chat, 'invite_link'):
                                if chat_identifier.replace('+', '') in str(dialog.chat.invite_link):
                                    chat = dialog.chat
                                    break
                    else:
                        # Public chat by username
                        chat = await self.user_client.get_chat(chat_identifier)
                except Exception as e:
                    logger.error(f"[USER CLIENT] Failed to get existing chat: {e}")
                    return None
            except Exception as e:
                logger.error(f"[USER CLIENT] Failed to join chat: {e}")
                return None
            
            if not chat:
                logger.error("[USER CLIENT] Could not get chat info")
                return None
            
            # Check for active VC in this chat
            logger.info(f"[USER CLIENT] Checking for VC in: {chat.title}")
            vc_info = await self._check_chat_vc(chat)
            
            if not vc_info:
                logger.info(f"[USER CLIENT] No active VC in {chat.title}")
                # Return chat info with inactive VC
                vc_info = VCInfo(
                    chat_id=chat.id,
                    chat_title=chat.title or "Unknown",
                    chat_username=chat.username,
                    invite_link=invite_link,
                    is_active=False,
                    participants_count=0
                )
            else:
                logger.info(f"[USER CLIENT] Found active VC: {vc_info.participants_count} participants")
                vc_info.invite_link = invite_link
            
            return (chat.id, chat.title or "Unknown", vc_info)
            
        except InviteHashExpired:
            logger.error(f"[USER CLIENT] Invite link expired: {invite_link}")
            return None
        except InviteHashInvalid:
            logger.error(f"[USER CLIENT] Invalid invite link: {invite_link}")
            return None
        except Exception as e:
            logger.error(f"[USER CLIENT] Error processing invite link: {e}")
            return None
    
    async def _check_chat_vc(self, chat: Chat) -> Optional[VCInfo]:
        """Check if chat has active voice/video chat"""
        try:
            full_chat = await self.user_client.get_chat(chat.id)
            
            vc = None
            if hasattr(full_chat, 'video_chat') and full_chat.video_chat:
                vc = full_chat.video_chat
            elif hasattr(full_chat, 'voice_chat') and full_chat.voice_chat:
                vc = full_chat.voice_chat
            
            if vc and getattr(vc, 'is_active', False):
                participants = getattr(vc, 'participants_count', 0)
                call_id = getattr(vc, 'id', None)
                
                return VCInfo(
                    chat_id=chat.id,
                    chat_title=chat.title or "Unknown",
                    chat_username=full_chat.username,
                    call_id=call_id,
                    participants_count=participants,
                    is_active=True
                )
            
        except Exception as e:
            logger.debug(f"[USER CLIENT] Error checking VC in chat {chat.id}: {e}")
        
        return None
    
    async def check_voice_chats(self) -> Optional[VCInfo]:
        """Check for active voice chats in all joined groups"""
        try:
            async for dialog in self.user_client.get_dialogs():
                try:
                    chat = dialog.chat
                    if not chat:
                        continue
                    
                    if chat.type not in ["group", "supergroup", "channel"]:
                        continue
                    
                    vc_info = await self._check_chat_vc(chat)
                    
                    if vc_info and vc_info.is_active:
                        if not self._last_vc or self._last_vc.chat_id != vc_info.chat_id:
                            self._last_vc = vc_info
                            logger.info(f"✅ [USER CLIENT] Active VC found: {vc_info.chat_title}")
                            return vc_info
                        
                except Exception as e:
                    logger.debug(f"[USER CLIENT] Error checking chat: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"[USER CLIENT] VC detection error: {e}")
        
        return None
    
    async def monitor_loop(self, callback):
        """Continuous monitoring loop"""
        self._running = True
        logger.info("🔍 [USER CLIENT] VC monitoring started")
        
        check_count = 0
        
        while self._running:
            try:
                check_count += 1
                if check_count % 6 == 0:
                    logger.info(f"🔍 [USER CLIENT] Check #{check_count}")
                
                vc_info = await self.check_voice_chats()
                
                if vc_info:
                    logger.info(f"📞 [USER CLIENT] Active VC: {vc_info.chat_title}")
                    try:
                        await callback(vc_info)
                    except Exception as e:
                        logger.error(f"[USER CLIENT] Callback error: {e}")
                
                for _ in range(self.check_interval):
                    if not self._running:
                        break
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                logger.info("[USER CLIENT] Monitor loop cancelled")
                raise
            except Exception as e:
                logger.error(f"[USER CLIENT] Monitor loop error: {e}")
                await asyncio.sleep(5)
        
        logger.info("🛑 [USER CLIENT] Monitoring stopped")
    
    def stop(self):
        """Stop monitoring"""
        self._running = False
        logger.info("[USER CLIENT] Stop signal received")
