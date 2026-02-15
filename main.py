"""Dual-client application entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

from pyrogram import Client, idle

from attack_engine import AttackEngine
from bot_handler import BotHandler
from config import Config
from vc_detector import VCDetector


def setup_logging(log_file: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_file, encoding="utf-8")],
    )
    logging.getLogger("pyrogram").setLevel(logging.WARNING)


async def run() -> int:
    cfg = Config.from_env()
    setup_logging(cfg.log_file)

    bot = Client(
        "vc_monitor_bot",
        api_id=cfg.api_id,
        api_hash=cfg.api_hash,
        bot_token=cfg.bot_token,
    )
    user = Client(
        "vc_monitor_user",
        api_id=cfg.api_id,
        api_hash=cfg.api_hash,
        session_string=cfg.session_string,
    )

    engine = AttackEngine(max_threads=cfg.max_threads, max_duration=cfg.max_duration)

    await bot.start()
    await user.start()

    detector = VCDetector(user_client=user, scan_cooldown_seconds=cfg.scan_cooldown_seconds)
    handler = BotHandler(bot=bot, detector=detector, engine=engine, admin_id=cfg.admin_id, max_duration=cfg.max_duration)
    handler.register_diag_command()

    if cfg.admin_id is not None:
        await bot.send_message(cfg.admin_id, "✅ VC monitor is online. Use /scan to begin on-demand checks.")
    else:
        logging.warning("ADMIN_ID is not set. Restrict bot access by setting ADMIN_ID in the environment.")

    try:
        await idle()
    finally:
        engine.stop()
        await user.stop()
        await bot.stop()

    return 0


def main() -> None:
    if sys.platform.startswith("linux"):
        try:
            import uvloop

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except Exception:
            pass

    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
