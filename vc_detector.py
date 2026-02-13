"""
Voice Chat Detection Module
Monitors active voice chats in groups
"""

import asyncio
import logging
from typing import Optional
from dataclasses import dataclass
from pyrogram import Client
from pyrogram.types import Chat

logger = logging.getLogger(__name__)


@dataclass
class VCInfo:
    """Voice Chat information container"""
    chat_id: int
    chat_title: str
    call_id: Optional[int] = None
    participants_count: int = 0
    is_active: bool = False


class VoiceChatDetector:
    """Detects active voice chats in groups"""
    
    def __init__(self, user_client: Client, admin_id: int, check_interval: int = 10):
        self.user_client = user_client
        self.admin_id = admin_id
        self.check_interval = check_interval
        self._last_vc: Optional[VCInfo] = None
        self._running = False
    
    async def check_voice_chats(self) -> Optional[VCInfo]:
        """Check for active voice chats in groups"""
        try:
            # Get all dialogs (chats)
            async for dialog in self.user_client.get_dialogs():
                try:
                    chat = dialog.chat
                    if not chat:
                        continue
                    
                    # Only check groups and channels (not private chats)
                    if chat.type not in ["group", "supergroup", "channel"]:
                        continue
                    
                    # Check for active voice/video chat
                    vc_info = await self._check_chat_vc(chat)
                    
                    if vc_info and vc_info.is_active:
                        # Only return if it's a new/different VC
                        if not self._last_vc or self._last_vc.chat_id != vc_info.chat_id:
                            self._last_vc = vc_info
                            logger.info(f"✅ Active VC found: {vc_info.chat_title} (ID: {vc_info.chat_id})")
                            return vc_info
                        
                except Exception as e:
                    logger.debug(f"Error checking chat {getattr(chat, 'id', 'unknown')}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"VC detection error: {e}")
        
        return None
    
    async def _check_chat_vc(self, chat: Chat) -> Optional[VCInfo]:
        """Check if chat has an active voice/video chat"""
        try:
            # Get full chat info
            full_chat = await self.user_client.get_chat(chat.id)
            
            # Check for video_chat (newer Pyrogram versions) or voice_chat
            vc = None
            
            if hasattr(full_chat, 'video_chat') and full_chat.video_chat:
                vc = full_chat.video_chat
                logger.debug(f"Found video_chat in {chat.title}")
            elif hasattr(full_chat, 'voice_chat') and full_chat.voice_chat:
                vc = full_chat.voice_chat
                logger.debug(f"Found voice_chat in {chat.title}")
            
            if vc:
                is_active = getattr(vc, 'is_active', False)
                
                if is_active:
                    participants = getattr(vc, 'participants_count', 0)
                    call_id = getattr(vc, 'id', None)
                    
                    logger.debug(f"Active VC in {chat.title}: {participants} participants")
                    
                    return VCInfo(
                        chat_id=chat.id,
                        chat_title=chat.title or "Unknown",
                        call_id=call_id,
                        participants_count=participants,
                        is_active=True
                    )
            
        except Exception as e:
            logger.debug(f"Error getting VC info for chat {chat.id}: {e}")
        
        return None
    
    async def monitor_loop(self, callback):
        """Continuous monitoring loop"""
        self._running = True
        logger.info("🔍 VC monitoring started")
        logger.info(f"⏱️ Check interval: {self.check_interval} seconds")
        
        check_count = 0
        
        while self._running:
            try:
                check_count += 1
                if check_count % 6 == 0:  # Log every minute
                    logger.info(f"🔍 VC check #{check_count} - scanning for active voice chats...")
                
                vc_info = await self.check_voice_chats()
                
                if vc_info:
                    logger.info(f"📞 Active VC detected: {vc_info.chat_title}")
                    try:
                        await callback(vc_info)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
                
                # Sleep with cancellation check
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
