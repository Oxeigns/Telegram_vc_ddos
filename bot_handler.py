"""
Clean Bot Handler - Control Panel Style with Live Status
Fixed & Completed - No Missing Methods
"""

import asyncio
import logging
from typing import Dict, Any
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

# Parse mode compatibility check
try:
    from pyrogram.enums import ParseMode
    HTML = ParseMode.HTML
except ImportError:
    HTML = "HTML"

# In imports ka hona zaroori hai (utils.py aur config.py se)
from config import Config
from utils import parse_ip_port, format_number

logger = logging.getLogger("BotHandler")

# Global tracking dictionaries
states: Dict[int, Dict] = {}
status_tasks: Dict[int, asyncio.Task] = {}

class BotHandler:
    """Complete Control Panel Interface with Live Status Tracking"""
    
    def __init__(self, bot: Client, attack_engine, admin_id: int):
        self.bot = bot
        self.engine = attack_engine
        self.admin_id = admin_id
        self.logger = logging.getLogger("BotHandler")

    def register_handlers(self):
        """
        Main.py isko call karta hai. Saare decorators yahan define hain.
        """
        
        @self.bot.on_message(filters.command("start") & filters.private)
        async def start_cmd(_, message: Message):
            if message.from_user.id != self.admin_id:
                return await message.reply_text("⛔ <b>Unauthorized</b>", parse_mode=HTML)
            
            # Purana state clear karein
            states.pop(message.from_user.id, None)
            await self._send_menu(message)

        @self.bot.on_callback_query(filters.regex("^back_menu$"))
        async def back_menu_cb(_, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id: return
            
            await self._stop_user_task(callback.from_user.id)
            await self._send_menu(callback.message, edit=True)
            await callback.answer()

        @self.bot.on_callback_query(filters.regex("^start_test$"))
        async def start_test_cb(_, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id: return
            
            states[callback.from_user.id] = {'step': 'waiting_ip'}
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="back_menu")
            ]])
            
            await callback.edit_message_text(
                "🚀 <b>START NETWORK TEST</b>\n\n"
                "<b>Step 1/2:</b> Target Setup\n"
                "Send IP and Port in <code>IP:PORT</code> format.\n\n"
                "Example: <code>1.1.1.1:80</code>",
                reply_markup=keyboard,
                parse_mode=HTML
            )
            await callback.answer()

        @self.bot.on_callback_query(filters.regex("^stop_test$"))
        async def stop_cb(_, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id: return
            
            # Background task rokein
            await self._stop_user_task(callback.from_user.id)
            
            # Engine rokein
            self.engine.stop_attack()
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")
            ]])
            
            await callback.edit_message_text(
                "🛑 <b>ATTACK STOPPED</b>\n\n"
                "The engine has been signaled to stop all threads.",
                reply_markup=keyboard,
                parse_mode=HTML
            )
            await callback.answer("Attack Stopped", show_alert=True)

        @self.bot.on_callback_query(filters.regex("^confirm_attack_(.+)$"))
        async def confirm_attack_cb(_, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id: return
            
            # Data format: confirm_attack_IP_PORT
            try:
                data_parts = callback.data.split("_")
                ip = data_parts[2]
                port = int(data_parts[3])
                
                # Attack start karein
                success = self.engine.start_attack(ip, port, "udp")
                
                if success:
                    await callback.answer("🚀 Attack Launched!", show_alert=False)
                    await self._start_live_updates(callback.from_user.id, callback.message)
                else:
                    await callback.answer("❌ Error: Attack already running!", show_alert=True)
                    
            except Exception as e:
                self.logger.error(f"Launch error: {e}")
                await callback.answer("❌ critical Launch Error", show_alert=True)

        @self.bot.on_message(filters.text & filters.private)
        async def handle_text_input(_, message: Message):
            user_id = message.from_user.id
            if user_id != self.admin_id: return
            
            # Check karein agar user IP enter karne waale step par hai
            if user_id in states and states[user_id].get('step') == 'waiting_ip':
                parsed = parse_ip_port(message.text.strip())
                
                if not parsed:
                    return await message.reply_text(
                        "❌ <b>Invalid Format!</b>\nUse <code>IP:PORT</code>",
                        parse_mode=HTML
                    )
                
                ip, port = parsed
                states[user_id] = {'step': 'confirm', 'ip': ip, 'port': port}
                
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🚀 LAUNCH", callback_data=f"confirm_attack_{ip}_{port}"),
                    InlineKeyboardButton("❌ CANCEL", callback_data="back_menu")
                ]])
                
                await message.reply_text(
                    f"🎯 <b>TARGET CONFIRMED</b>\n\n"
                    f"<b>IP:</b> <code>{ip}</code>\n"
                    f"<b>Port:</b> <code>{port}</code>\n"
                    f"<b>Method:</b> <code>UDP Flood</code>\n\n"
                    "Ready to start the test?",
                    reply_markup=keyboard,
                    parse_mode=HTML
                )

    # --- Helper Methods ---

    async def _send_menu(self, message, edit=False):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Start Test", callback_data="start_test")],
            [InlineKeyboardButton("📊 Status", callback_data="show_status"),
             InlineKeyboardButton("🛑 Stop", callback_data="stop_test")]
        ])
        
        text = (
            "🤖 <b>STRESSER CONTROL PANEL</b>\n\n"
            "<b>System:</b> <code>READY</code> ✅\n"
            "<b>Admin:</b> <code>Verified</code> 🛡️\n\n"
            "Select an action from the buttons below:"
        )
        
        if edit:
            await message.edit_text(text, reply_markup=keyboard, parse_mode=HTML)
        else:
            await message.reply_text(text, reply_markup=keyboard, parse_mode=HTML)

    async def _stop_user_task(self, user_id: int):
        """Purane update loop ko khatam karne ke liye"""
        if user_id in status_tasks:
            status_tasks[user_id].cancel()
            try:
                await status_tasks[user_id]
            except asyncio.CancelledError:
                pass
            status_tasks.pop(user_id, None)

    async def _start_live_updates(self, user_id: int, message):
        """Naya update task shuru karein"""
        await self._stop_user_task(user_id)
        task = asyncio.create_task(self._live_status_updater(user_id, message))
        status_tasks[user_id] = task

    async def _live_status_updater(self, user_id: int, message):
        """Background task jo har 4 second baad stats update karega"""
        try:
            while self.engine.stats.is_running:
                stats = self.engine.get_status()
                
                # Progress Bar Logic
                prog = min(100, (stats['progress'] / max(stats['max'], 1)) * 100)
                bar = "█" * int(prog / 10) + "░" * (10 - int(prog / 10))
                
                text = (
                    f"⚡ <b>ATTACK IN PROGRESS</b> ⚡\n\n"
                    f"<b>Target:</b> <code>{stats['target']}:{stats['port']}</code>\n"
                    f"<b>Progress:</b> <code>[{bar}] {prog:.1f}%</code>\n"
                    f"<b>Requests:</b> <code>{format_number(stats['progress'])}</code>\n"
                    f"<b>RPS:</b> <code>{stats['rps']}</code>\n"
                    f"<b>Time:</b> <code>{stats['duration']:.1f}s</code>\n\n"
                    "<i>Updating live every 4s...</i>"
                )
                
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🛑 STOP ATTACK", callback_data="stop_test")
                ]])
                
                try:
                    await message.edit_text(text, reply_markup=keyboard, parse_mode=HTML)
                except Exception:
                    # Agar user ne message delete kiya ya edit fail hua
                    break
                
                await asyncio.sleep(4) # Flood protection gap
                
            # Attack khatam hone par final message
            final_stats = self.engine.get_status()
            await message.edit_text(
                "✅ <b>TEST FINISHED</b>\n\n"
                f"Total Packets: <code>{format_number(final_stats['progress'])}</code>\n"
                "System is now <b>IDLE</b>.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Menu", callback_data="back_menu")
                ]]),
                parse_mode=HTML
            )
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Live updater error: {e}")
