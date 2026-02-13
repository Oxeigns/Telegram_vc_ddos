"""
Clean Bot Handler - Control Panel Style with Live Status
"""

import asyncio
import logging
import random
from typing import Optional, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Parse mode fix
try:
    from pyrogram.enums import ParseMode
    HTML = ParseMode.HTML
except ImportError:
    HTML = "HTML"

from config import Config, ATTACK_METHODS
from utils import is_valid_ip, parse_ip_port, format_number

logger = logging.getLogger(__name__)

# User states
states: Dict[int, Dict] = {}
# Active status messages for live updates
status_messages: Dict[int, Any] = {}


class BotHandler:
    """Clean Control Panel Interface with Live Status"""
    
    def __init__(self, bot: Client, attack_engine, admin_id: int):
        self.bot = bot
        self.engine = attack_engine
        self.admin_id = admin_id
        self.logger = logging.getLogger(__name__)
        self._register_handlers()
    
    def _register_handlers(self):
        
        @self.bot.on_message(filters.command("start") & filters.private)
        async def start_cmd(client, message):
            if message.from_user.id != self.admin_id:
                await message.reply_text("⛔ <b>Unauthorized</b>", parse_mode=HTML)
                return
            
            states.pop(message.from_user.id, None)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Start Test", callback_data="start_test")],
                [InlineKeyboardButton("📊 Status", callback_data="show_status"),
                 InlineKeyboardButton("🛑 Stop", callback_data="stop_test")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="show_settings")]
            ])
            
            text = (
                "╔════════════════════════╗\n"
                "║   🤖 <b>CONTROL PANEL</b>   ║\n"
                "╚════════════════════════╝\n\n"
                "<b>System Status:</b> <code>ONLINE</code> ✅\n"
                f"<b>Threads:</b> <code>{Config.THREAD_COUNT}</code>\n"
                f"<b>Max Requests:</b> <code>{format_number(Config.MAX_REQUESTS)}</code>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "<b>Select an option:</b>"
            )
            
            await message.reply_text(text, reply_markup=keyboard, parse_mode=HTML)
        
        
        @self.bot.on_callback_query(filters.regex("^start_test$"))
        async def start_test_cb(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            states[callback.from_user.id] = {'step': 'waiting_ip'}
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
            
            await callback.edit_message_text(
                "🚀 <b>START NETWORK TEST</b>\n\n"
                "<b>Step 1/3:</b> Enter Target\n\n"
                "Send target IP and port:\n"
                "<code>IP:PORT</code>\n\n"
                "<b>Examples:</b>\n"
                "• <code>192.168.1.1:80</code>\n"
                "• <code>10.0.0.1:8080</code>",
                reply_markup=keyboard,
                parse_mode=HTML
            )
        
        
        @self.bot.on_callback_query(filters.regex("^show_status$"))
        async def status_cb(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            stats = self.engine.get_status()
            
            if stats['running']:
                progress = min(100, (stats['progress'] / max(stats['max'], 1)) * 100)
                bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
                
                text = (
                    "🚀 <b>LIVE STATUS</b>\n\n"
                    f"<b>Target:</b> <code>{stats['target']}:{stats['port']}</code>\n"
                    f"<b>Progress:</b> <code>[{bar}] {progress:.1f}%</code>\n"
                    f"<b>Requests:</b> <code>{format_number(stats['progress'])}/{format_number(stats['max'])}</code>\n"
                    f"<b>Success:</b> <code>{format_number(stats['successful'])}</code>\n"
                    f"<b>Failed:</b> <code>{format_number(stats['failed'])}</code>\n"
                    f"<b>RPS:</b> <code>{stats['rps']:.2f}</code>\n"
                    f"<b>Time:</b> <code>{stats['duration']:.1f}s</code>\n\n"
                    "<i>Auto-updating every 3 seconds...</i>"
                )
            else:
                text = (
                    "📊 <b>SYSTEM STATUS</b>\n\n"
                    "<b>State:</b> <code>IDLE</code> ⚪\n"
                    "No active test running.\n\n"
                    "Click <b>🚀 Start Test</b> to begin"
                )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="show_status"),
                 InlineKeyboardButton("🛑 Stop", callback_data="stop_test")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_menu")]
            ])
            
            await callback.edit_message_text(text, reply_markup=keyboard, parse_mode=HTML)
            
            # Start live updates if running
            if stats['running'] and callback.from_user.id not in status_messages:
                status_messages[callback.from_user.id] = callback.message
                asyncio.create_task(self._live_status_updater(callback.from_user.id, callback.message))
        
        
        @self.bot.on_callback_query(filters.regex("^stop_test$"))
        async def stop_cb(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            if not self.engine.stats.is_running:
                await callback.answer("No active test!", show_alert=True)
                return
            
            # Stop live updates
            status_messages.pop(callback.from_user.id, None)
            
            stats = self.engine.stop_attack()
            states.pop(callback.from_user.id, None)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
            ])
            
            text = (
                "🛑 <b>TEST STOPPED</b>\n\n"
                "<b>Final Results:</b>\n"
                f"├ Total: <code>{format_number(stats['total'])}</code>\n"
                f"├ Success: <code>{format_number(stats['successful'])}</code>\n"
                f"├ Failed: <code>{format_number(stats['failed'])}</code>\n"
                f"├ Duration: <code>{stats['duration']:.2f}s</code>\n"
                f"└ RPS: <code>{stats['rps']:.2f}</code>"
            )
            
            await callback.edit_message_text(text, reply_markup=keyboard, parse_mode=HTML)
        
        
        @self.bot.on_callback_query(filters.regex("^show_settings$"))
        async def settings_cb(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_menu")]
            ])
            
            text = (
                "⚙️ <b>SETTINGS</b>\n\n"
                "<b>Configuration:</b>\n"
                f"├ Max Requests: <code>{format_number(Config.MAX_REQUESTS)}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"├ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n"
                f"└ Method: <code>UDP Flood</code>\n\n"
                "<i>Edit via Heroku Config Vars</i>"
            )
            
            await callback.edit_message_text(text, reply_markup=keyboard, parse_mode=HTML)
        
        
        @self.bot.on_callback_query(filters.regex("^(cancel|back_menu)$"))
        async def cancel_cb(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            states.pop(callback.from_user.id, None)
            status_messages.pop(callback.from_user.id, None)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Start Test", callback_data="start_test")],
                [InlineKeyboardButton("📊 Status", callback_data="show_status"),
                 InlineKeyboardButton("🛑 Stop", callback_data="stop_test")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="show_settings")]
            ])
            
            text = (
                "╔════════════════════════╗\n"
                "║   🤖 <b>CONTROL PANEL</b>   ║\n"
                "╚════════════════════════╝\n\n"
                "<b>System Status:</b> <code>ONLINE</code> ✅\n"
                f"<b>Threads:</b> <code>{Config.THREAD_COUNT}</code>\n"
                f"<b>Max Requests:</b> <code>{format_number(Config.MAX_REQUESTS)}</code>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            
            await callback.edit_message_text(text, reply_markup=keyboard, parse_mode=HTML)
        
        
        @self.bot.on_callback_query(filters.regex("^confirm_attack_(.+)$"))
        async def confirm_attack_cb(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id:
                return
            
            try:
                data = callback.data.replace("confirm_attack_", "").split("_")
                ip, port = data[0], int(data[1])
                
                await callback.edit_message_text(
                    f"⏳ <b>Starting Test...</b>\n"
                    f"Target: <code>{ip}:{port}</code>",
                    parse_mode=HTML
                )
                
                success = self.engine.start_attack(ip, port, "udp")
                
                if success:
                    # Create status message
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛑 Stop Test", callback_data="stop_test")],
                        [InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]
                    ])
                    
                    text = (
                        "🚀 <b>TEST STARTED!</b>\n\n"
                        f"<b>Target:</b> <code>{ip}:{port}</code>\n"
                        f"<b>Method:</b> <code>UDP Flood</code>\n\n"
                        "⏳ <b>Initializing...</b>\n\n"
                        "<i>Live updates starting...</i>"
                    )
                    
                    msg = await callback.edit_message_text(text, reply_markup=keyboard, parse_mode=HTML)
                    
                    # Start live status updater
                    status_messages[callback.from_user.id] = msg
                    asyncio.create_task(self._live_status_updater(callback.from_user.id, msg))
                    
                else:
                    await callback.edit_message_text(
                        "❌ <b>Failed!</b>\nTest already running?",
                        parse_mode=HTML
                    )
                    
            except Exception as e:
                self.logger.error(f"Attack error: {e}")
                await callback.edit_message_text(f"❌ Error: {str(e)[:100]}", parse_mode=HTML)
        
        
        @self.bot.on_message(filters.text & filters.private)
        async def handle_input(client, message):
            if message.from_user.id != self.admin_id:
                return
            
            user_id = message.from_user.id
            text = message.text.strip()
            
            if user_id in states and states[user_id].get('step') == 'waiting_ip':
                parsed = parse_ip_port(text)
                
                if not parsed:
                    await message.reply_text(
                        "❌ <b>Invalid Format!</b>\n\n"
                        "Use: <code>IP:PORT</code>\n"
                        "Ex: <code>192.168.1.1:80</code>",
                        parse_mode=HTML
                    )
                    return
                
                ip, port = parsed
                states[user_id] = {'step': 'confirm', 'ip': ip, 'port': port}
                
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🚀 START", callback_data=f"confirm_attack_{ip}_{port}"),
                        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                    ]
                ])
                
                await message.reply_text(
                    f"🎯 <b>Confirm Target</b>\n\n"
                    f"<b>IP:</b> <code>{ip}</code>\n"
                    f"<b>Port:</b> <code>{port}</code>\n"
                    f"<b>Method:</b> <code>UDP Flood</code>\n"
                    f"<b>Threads:</b> <code>{Config.THREAD_COUNT}</code>\n\n"
                    f"Click <b>🚀 START</b> to begin:",
                    reply_markup=keyboard,
                    parse_mode=HTML
                )
    
    
    async def _live_status_updater(self, user_id: int, message):
        """Background task for live status updates"""
        try:
            update_count = 0
            while self.engine.stats.is_running and user_id in status_messages:
                await asyncio.sleep(3)  # Update every 3 seconds
                
                if not self.engine.stats.is_running:
                    break
                
                # Check if still tracking this message
                if status_messages.get(user_id) != message:
                    break
                
                stats = self.engine.get_status()
                progress = min(100, (stats['progress'] / max(stats['max'], 1)) * 100)
                bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
                
                # Different animation frames
                anim_frames = ["⚡", "🔥", "💥", "⚡"]
                anim = anim_frames[update_count % len(anim_frames)]
                
                text = (
                    f"{anim} <b>LIVE ATTACK STATUS</b> {anim}\n\n"
                    f"<b>Target:</b> <code>{stats['target']}:{stats['port']}</code>\n"
                    f"<b>Progress:</b> <code>[{bar}] {progress:.1f}%</code>\n"
                    f"<b>Requests:</b> <code>{format_number(stats['progress'])}/{format_number(stats['max'])}</code>\n"
                    f"<b>Success:</b> <code>{format_number(stats['successful'])}</code> ✅\n"
                    f"<b>Failed:</b> <code>{format_number(stats['failed'])}</code> ❌\n"
                    f"<b>RPS:</b> <code>{stats['rps']:.2f}</code> req/s\n"
                    f"<b>Duration:</b> <code>{stats['duration']:.1f}s</code>\n"
                    f"<b>Threads:</b> <code>{stats['threads_active']}/{Config.THREAD_COUNT}</code>\n\n"
                    f"<i>Updating... ({update_count})</i>"
                )
                
                try:
                    await message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🛑 STOP NOW", callback_data="stop_test")],
                            [InlineKeyboardButton("🔙 Hide (keep running)", callback_data="back_menu")]
                        ]),
                        parse_mode=HTML
                    )
                    update_count += 1
                except Exception as e:
                    # Message might be deleted or other error
                    if "MESSAGE_NOT_MODIFIED" not in str(e):
                        self.logger.debug(f"Status update error: {e}")
                    break
            
            # Attack finished or stopped
            if user_id in status_messages:
                stats = self.engine.get_status()
                
                text = (
                    "✅ <b>ATTACK COMPLETED!</b>\n\n"
                    f"<b>Target:</b> <code>{stats['target']}:{stats['port']}</code>\n"
                    f"<b>Total Requests:</b> <code>{format_number(stats['progress'])}</code>\n"
                    f"<b>Successful:</b> <code>{format_number(stats['successful'])}</code> ✅\n"
                    f"<b>Failed:</b> <code>{format_number(stats['failed'])}</code> ❌\n"
                    f"<b>Duration:</b> <code>{stats['duration']:.2f}s</code>\n"
                    f"<b>Avg RPS:</b> <code>{stats['rps']:.2f}</code>\n\n"
                    "<b>Status:</b> <code>FINISHED</code> ✅"
                )
                
                try:
                    await message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
                        ]),
                        parse_mode=HTML
                    )
                except:
                    pass
                
                status_messages.pop(user_id, None)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Live updater error: {e}")
