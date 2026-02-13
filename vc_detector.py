"""
Voice Chat Detection Module
Monitors active voice chats in groups and handles invite links
"""

import asyncio
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from pyrogram import Client
from pyrogram.types import Chat
from pyrogram.errors import InviteHashExpired, InviteHashInvalid, ChannelInvalid

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
    server_ip: Optional[str] = None  # Store resolved IP


class VoiceChatDetector:
    """Detects active voice chats in groups and resolves invite links"""
    
    def __init__(self, user_client: Client, admin_id: int, check_interval: int = 10):
        self.user_client = user_client
        self.admin_id = admin_id
        self.check_interval = check_interval
        self._last_vc: Optional[VCInfo] = None
        self._running = False
    
    async def resolve_invite_link(self, invite_link: str) -> Optional[Tuple[int, str, str]]:
        """
        Resolve invite link to get chat info
        Returns: (chat_id, chat_title, invite_link) or None
        """
        try:
            logger.info(f"Resolving invite link: {invite_link}")
            
            # Try to join/get chat from invite link
            try:
                chat = await self.user_client.join_chat(invite_link)
                if chat:
                    logger.info(f"Successfully joined/resolved chat: {chat.title} (ID: {chat.id})")
                    return (chat.id, chat.title, invite_link)
            except Exception as e:
                logger.warning(f"join_chat failed: {e}, trying get_chat...")
            
            # Alternative: try to get chat info without joining
            try:
                # For public groups, we can get info directly
                if not invite_link.startswith('+'):
                    chat = await self.user_client.get_chat(invite_link)
                    if chat:
                        logger.info(f"Got chat info: {chat.title} (ID: {chat.id})")
                        return (chat.id, chat.title, invite_link)
            except Exception as e:
                logger.warning(f"get_chat failed: {e}")
            
            logger.error(f"Failed to resolve invite link: {invite_link}")
            return None
            
        except InviteHashExpired:
            logger.error(f"Invite link expired: {invite_link}")
            return None
        except InviteHashInvalid:
            logger.error(f"Invalid invite link: {invite_link}")
            return None
        except Exception as e:
            logger.error(f"Error resolving invite link: {e}")
            return None
    
    async def get_vc_from_chat(self, chat_id: int) -> Optional[VCInfo]:
        """Get voice chat info from a specific chat ID"""
        try:
            chat = await self.user_client.get_chat(chat_id)
            return await self._check_chat_vc(chat)
        except Exception as e:
            logger.error(f"Error getting VC from chat {chat_id}: {e}")
            return None
    
    async def check_voice_chats(self) -> Optional[VCInfo]:
        """Check for active voice chats in all joined groups"""
        try:
            async for dialog in self.user_client.get_dialogs():
                try:
                    chat = dialog.chat
                    if not chat:
                        continue
                    
                    # Only check groups and channels
                    if chat.type not in ["group", "supergroup", "channel"]:
                        continue
                    
                    vc_info = await self._check_chat_vc(chat)
                    
                    if vc_info and vc_info.is_active:
                        if not self._last_vc or self._last_vc.chat_id != vc_info.chat_id:
                            self._last_vc = vc_info
                            logger.info(f"✅ Active VC found: {vc_info.chat_title}")
                            return vc_info
                        
                except Exception as e:
                    logger.debug(f"Error checking chat: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"VC detection error: {e}")
        
        return None
    
    async def _check_chat_vc(self, chat: Chat) -> Optional[VCInfo]:
        """Check if chat has an active voice/video chat"""
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
                
                # Get chat invite link if available
                invite_link = None
                if hasattr(full_chat, 'invite_link') and full_chat.invite_link:
                    invite_link = full_chat.invite_link
                
                return VCInfo(
                    chat_id=chat.id,
                    chat_title=chat.title or "Unknown",
                    chat_username=full_chat.username,
                    invite_link=invite_link,
                    call_id=call_id,
                    participants_count=participants,
                    is_active=True
                )
            
        except Exception as e:
            logger.debug(f"Error checking VC in chat {chat.id}: {e}")
        
        return None
    
    async def monitor_loop(self, callback):
        """Continuous monitoring loop"""
        self._running = True
        logger.info("🔍 VC monitoring started")
        
        check_count = 0
        
        while self._running:
            try:
                check_count += 1
                if check_count % 6 == 0:
                    logger.info(f"🔍 VC check #{check_count}")
                
                vc_info = await self.check_voice_chats()
                
                if vc_info:
                    logger.info(f"📞 Active VC detected: {vc_info.chat_title}")
                    try:
                        await callback(vc_info)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
                
                for _ in range(self.check_interval):
                    if not self._running:
                        break
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                logger.info("Monitor loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(5)
        
        logger.info("🛑 VC monitoring stopped")
    
    def stop(self):
        """Stop monitoring"""
        self._running = False
        logger.info("Stop signal received")
