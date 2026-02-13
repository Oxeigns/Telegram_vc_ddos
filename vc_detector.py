"""
Voice Chat Detection Module
Monitors user's VC presence across chats
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pyrogram import Client
from pyrogram.raw.functions.phone import GetGroupCall
from pyrogram.raw.types import InputGroupCall
from pyrogram.errors import BadRequest, Forbidden

logger = logging.getLogger(__name__)


@dataclass
class VCInfo:
    """Voice Chat information container"""
    chat_id: int
    chat_title: str
    call_id: int
    participants_count: int
    is_active: bool
    

class VoiceChatDetector:
    """Detects admin presence in voice chats"""
    
    def __init__(self, user_client: Client, admin_id: int, check_interval: int = 10):
        self.user_client = user_client
        self.admin_id = admin_id
        self.check_interval = check_interval
        self._last_vc: Optional[VCInfo] = None
        self._running = False
    
    async def check_voice_chats(self) -> Optional[VCInfo]:
        """Check if admin is in any active voice chat"""
        try:
            # Iterate through all dialogs
            async for dialog in self.user_client.get_dialogs():
                chat = dialog.chat
                if not chat:
                    continue
                
                try:
                    # Check for voice chat using raw functions
                    # Note: This requires the full chat info
                    full_chat = await self.user_client.get_chat(chat.id)
                    
                    # Check if there's an active voice chat
                    if hasattr(full_chat, 'voice_chat') and full_chat.voice_chat:
                        vc = full_chat.voice_chat
                        
                        if vc and getattr(vc, 'is_active', False):
                            # Check if admin is participant (via participants list)
                            participants = await self._get_participants(chat.id, vc.id)
                            
                            if self.admin_id in participants:
                                vc_info = VCInfo(
                                    chat_id=chat.id,
                                    chat_title=chat.title or chat.first_name or "Unknown",
                                    call_id=vc.id,
                                    participants_count=len(participants),
                                    is_active=True
                                )
                                
                                # Only return if it's a new/different VC
                                if not self._last_vc or self._last_vc.chat_id != vc_info.chat_id:
                                    self._last_vc = vc_info
                                    return vc_info
                                    
                except (BadRequest, Forbidden) as e:
                    logger.debug(f"Cannot access VC in chat {chat.id}: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error checking chat {chat.id}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"VC detection error: {e}")
        
        return None
    
    async def _get_participants(self, chat_id: int, call_id: int) -> list:
        """Get voice chat participants"""
        try:
            # Use raw function to get participants
            result = await self.user_client.invoke(
                GetGroupCall(
                    call=InputGroupCall(
                        id=call_id,
                        access_hash=0  # This needs to be fetched properly
                    ),
                    limit=200
                )
            )
            
            # Extract user IDs from participants
            participants = []
            for participant in getattr(result, 'participants', []):
                peer = getattr(participant, 'peer', None)
                if peer:
                    user_id = getattr(peer, 'user_id', None)
                    if user_id:
                        participants.append(user_id)
            
            return participants
            
        except Exception as e:
            logger.error(f"Failed to get participants: {e}")
            return []
    
    async def monitor_loop(self, callback):
        """Continuous monitoring loop"""
        self._running = True
        logger.info("VC monitoring started")
        
        while self._running:
            try:
                vc_info = await self.check_voice_chats()
                if vc_info:
                    logger.info(f"Admin found in VC: {vc_info.chat_title}")
                    await callback(vc_info)
                    
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    def stop(self):
        """Stop monitoring"""
        self._running = False
        logger.info("VC monitoring stopped")
