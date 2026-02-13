"""
Telegram Bot Handlers
Bot is only for UI - all group operations use USER SESSION via vc_detector
"""

import asyncio
import logging
import random
from typing import Optional, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified

# Fix: Import ParseMode from pyrogram.enums
try:
    from pyrogram.enums import ParseMode
    HTML_MODE = ParseMode.HTML
except ImportError:
    HTML_MODE = "HTML"

from config import Config, ATTACK_METHODS
from utils import get_public_ip, is_valid_ip, parse_ip_port, format_number, parse_telegram_invite_link
from vc_detector import VCInfo

logger = logging.getLogger(__name__)

# State management for user flows
user_states: Dict[int, Dict[str, Any]] = {}


class BotHandler:
    """Manages bot UI - all group operations delegated to vc_detector (user session)"""
    
    def __init__(self, bot: Client, attack_engine, admin_id: int, vc_detector=None):
        self.bot = bot  # BOT CLIENT - only for UI
        self.attack_engine = attack_engine
        self.admin_id = admin_id
        self.vc_detector = vc_detector  # Uses USER SESSION internally
        self.logger = logging.getLogger(__name__)
        
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all message handlers"""
        
        @self.bot.on_message(filters.command("start") & filters.private)
        async def start_handler(client, message):
            if message.from_user.id != self.admin_id:
                await message.reply_text("⛔ <b>Unauthorized Access</b>", parse_mode=HTML_MODE)
                return
            
            # Clear user state
            if message.from_user.id in user_states:
                del user_states[message.from_user.id]
            
            status = "🟢 <b>MONITORING</b>" if Config.MONITORING_MODE else "⚪ <b>STANDBY</b>"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Status", callback_data="show_status"),
                 InlineKeyboardButton("🔗 Manual Target", callback_data="manual_target")]
            ])
            
            text = (
                "🤖 <b>VC Monitor Bot</b>\n\n"
                f"Status: {status}\n"
                "Uses your User Session to join groups and detect VCs\n\n"
                "<b>How to use:</b>\n"
                "1. Join a Voice Chat in any group\n"
                "2. Bot will auto-detect via your user session\n"
                "3. Or use Manual Target to send invite link\n\n"
                "<b>Configuration:</b>\n"
                f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"├ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n"
                f"└ Check Interval: <code>{Config.VC_CHECK_INTERVAL}s</code>"
            )
            
            try:
                await message.reply_text(text, reply_markup=keyboard, parse_mode=HTML_MODE)
            except Exception as e:
                self.logger.error(f"Start handler error: {e}")
        
        @self.bot.on_callback_query(filters.regex("^manual_target$"))
        async def manual_target_callback(client, callback: CallbackQuery):
            """Handle manual target button"""
            if callback.from_user.id != self.admin_id:
                return
            
            # Set state to waiting for invite link
            user_states[callback.from_user.id] = {'state': 'waiting_for_invite_link'}
            
            try:
                await callback.edit_message_text(
                    "🔗 <b>Manual Target - Send Invite Link</b>\n\n"
                    "Your <b>User Session</b> will:\n"
                    "1. Join the group using invite link\n"
                    "2. Check for active Voice Chat\n"
                    "3. Extract target for attack\n\n"
                    "<b>Send invite link:</b>\n"
                    "• <code>https://t.me/+AbCdEfGhIjK</code>\n"
                    "• <code>https://t.me/groupname</code>\n"
                    "• <code>@groupname</code>\n\n"
                    "Or send IP:PORT directly:\n"
                    "• <code>192.168.1.1:8080</code>",
                    parse_mode=HTML_MODE
                )
            except Exception as e:
                self.logger.error(f"Manual target callback error: {e}")
        
        @self.bot.on_callback_query(filters.regex("^attack_cancel$"))
        async def cancel_attack_callback(client, callback: CallbackQuery):
            """Handle cancel button"""
            if callback.from_user.id != self.admin_id:
                return
            
            # Clear user state
            if callback.from_user.id in user_states:
                del user_states[callback.from_user.id]
            
            try:
                await callback.edit_message_text(
                    "❌ <b>Cancelled</b>\n\n"
                    "Operation cancelled. No requests sent.",
                    parse_mode=HTML_MODE
                )
            except Exception as e:
                self.logger.error(f"Cancel error: {e}")
        
        @self.bot.on_callback_query(filters.regex("^attack_(.+)
    
    async def notify_vc_detected(self, vc_info: VCInfo):
        """Notify admin when VC detected via monitoring"""
        try:
            server_ip = get_public_ip()
            unique_id = random.randint(1000, 9999)
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Attack", callback_data=f"attack_{server_ip}_{Config.ATTACK_PORT}_{unique_id}_yes"),
                    InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
                ]
            ])
            
            text = (
                "🔍 <b>Voice Chat Auto-Detected!</b>\n\n"
                f"📍 Group: <code>{vc_info.chat_title}</code>\n"
                f"👥 Participants: <code>{vc_info.participants_count}</code>\n\n"
                f"🌐 Target: <code>{server_ip}:{Config.ATTACK_PORT}</code>\n\n"
                f"Attack this target?"
            )
            
            await self.bot.send_message(
                self.admin_id,
                text,
                reply_markup=keyboard,
                parse_mode=HTML_MODE
            )
        except Exception as e:
            self.logger.error(f"Notify VC error: {e}")
    
    async def _process_invite_link_input(self, message, link: str):
        """Process invite link using vc_detector (which uses user session)"""
        user_id = message.from_user.id
        
        # Check if vc_detector is available
        if not self.vc_detector:
            await message.reply_text(
                "❌ <b>Error:</b> VC Detector not initialized properly!",
                parse_mode=HTML_MODE
            )
            if user_id in user_states:
                del user_states[user_id]
            return
        
        # Show processing message
        processing_msg = await message.reply_text(
            "⏳ <b>Processing via User Session...</b>\n\n"
            f"Link: <code>{link}</code>\n"
            "• Joining group...\n"
            "• Checking for Voice Chat...",
            parse_mode=HTML_MODE
        )
        
        try:
            # Use vc_detector to process invite link (uses USER SESSION internally)
            result = await self.vc_detector.process_invite_link(link)
            
            if not result:
                await processing_msg.edit_text(
                    "❌ <b>Failed to process invite link!</b>\n\n"
                    "Possible reasons:\n"
                    "• Link expired or invalid\n"
                    "• User session banned from group\n"
                    "• Group doesn't exist\n"
                    "• Rate limit hit (try again later)",
                    parse_mode=HTML_MODE
                )
                if user_id in user_states:
                    del user_states[user_id]
                return
            
            chat_id, chat_title, vc_info = result
            
            # Check if VC is active
            if not vc_info or not vc_info.is_active:
                await processing_msg.edit_text(
                    f"⚠️ <b>No Active Voice Chat!</b>\n\n"
                    f"Group: <code>{chat_title}</code>\n\n"
                    f"Successfully joined, but no active VC found.\n"
                    f"Please start a Voice Chat in the group first, then try again.",
                    parse_mode=HTML_MODE
                )
                if user_id in user_states:
                    del user_states[user_id]
                return
            
            # SUCCESS - VC found! Get server IP and show confirmation
            server_ip = get_public_ip()
            target_port = Config.ATTACK_PORT
            
            # Update user state
            user_states[user_id] = {
                'state': 'ready_to_attack',
                'chat_id': chat_id,
                'chat_title': chat_title,
                'vc_info': vc_info,
                'target_ip': server_ip,
                'target_port': target_port
            }
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ YES - Attack", callback_data=f"attack_{server_ip}_{target_port}_{random.randint(1000,9999)}_yes"),
                    InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
                ]
            ])
            
            await processing_msg.edit_text(
                f"✅ <b>Voice Chat Found!</b>\n\n"
                f"📍 <b>Group:</b> <code>{chat_title}</code>\n"
                f"👥 <b>Participants:</b> <code>{vc_info.participants_count}</code>\n"
                f"🔊 <b>Status:</b> <code>Active</code>\n\n"
                f"🌐 <b>Target IP:</b> <code>{server_ip}</code>\n"
                f"🔌 <b>Port:</b> <code>{target_port}</code>\n\n"
                f"⚙️ <b>Attack Settings:</b>\n"
                f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"└ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n\n"
                f"Start attack on this target?",
                reply_markup=keyboard,
                parse_mode=HTML_MODE
            )
            
        except Exception as e:
            self.logger.error(f"Error processing invite link: {e}")
            await processing_msg.edit_text(
                f"❌ <b>Error!</b>\n\n"
                f"<code>{str(e)[:200]}</code>\n\n"
                f"Please check logs and try again.",
                parse_mode=HTML_MODE
            )
            if user_id in user_states:
                del user_states[user_id]
    
    async def _show_attack_confirmation(self, message, ip: str, port: int, source: str):
        """Show attack confirmation with YES/NO buttons"""
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ YES - Attack", callback_data=f"attack_{ip}_{port}_{random.randint(1000,9999)}_yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
            ]
        ])
        
        text = (
            f"🎯 <b>Confirm Target</b>\n"
            f"Source: <code>{source}</code>\n\n"
            f"🌐 IP: <code>{ip}</code>\n"
            f"🔌 Port: <code>{port}</code>\n\n"
            f"⚙️ Attack Settings:\n"
            f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
            f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
            f"└ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n\n"
            f"Start attack?"
        )
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=HTML_MODE)
