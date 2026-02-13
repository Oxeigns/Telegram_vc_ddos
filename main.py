"""
VC Monitor Bot - Main Entry Point
Production-ready deployment for Heroku
"""

import asyncio
import logging
import sys
from datetime import datetime

from pyrogram import Client, idle
from pyrogram.errors import SessionExpired, AuthKeyInvalid

from config import Config
from utils import get_public_ip
from attack_engine import AttackEngine
from vc_detector import VoiceChatDetector
from bot_handler import BotHandler


# ---------------- LOGGING SETUP ---------------- #

def setup_logging():
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(Config.LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    return logging.getLogger(__name__)


# ---------------- BOT MANAGER ---------------- #

class BotManager:
    def __init__(self):
        self.logger = setup_logging()
        self.user_client: Client | None = None
        self.bot: Client | None = None
        self.attack_engine: AttackEngine | None = None
        self.vc_detector: VoiceChatDetector | None = None
        self.bot_handler: BotHandler | None = None
        self.monitor_task: asyncio.Task | None = None
        self._running = False

    # ---------------- INITIALIZE ---------------- #

    async def initialize(self) -> bool:
        self.logger.info("=" * 50)
        self.logger.info("VC Monitor Bot - Starting Initialization")
        self.logger.info(f"Time: {datetime.now().isoformat()}")
        self.logger.info(f"Server IP: {get_public_ip()}")
        self.logger.info("=" * 50)

        if not Config.validate():
            self.logger.error("Configuration validation failed!")
            return False

        try:
            # User client
            self.user_client = Client(
                "user_session",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                session_string=Config.SESSION_STRING,
                no_updates=False,
            )

            # Bot client
            self.bot = Client(
                "bot",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=Config.BOT_TOKEN,
                workers=4,
                parse_mode="html",
            )

            # Components
            self.attack_engine = AttackEngine(
                max_requests=Config.MAX_REQUESTS,
                thread_count=Config.THREAD_COUNT,
                timeout=Config.ATTACK_TIMEOUT,
            )

            self.vc_detector = VoiceChatDetector(
                user_client=self.user_client,
                admin_id=Config.ADMIN_USER_ID,
                check_interval=Config.VC_CHECK_INTERVAL,
            )

            # Start clients
            await self.user_client.start()
            await self.bot.start()

            self.bot_handler = BotHandler(
                bot=self.bot,
                attack_engine=self.attack_engine,
                admin_id=Config.ADMIN_USER_ID,
            )

            # Startup message
            await self.bot.send_message(
                Config.ADMIN_USER_ID,
                f"🤖 <b>Bot Started Successfully</b>\n\n"
                f"🌐 Server IP: <code>{get_public_ip()}</code>\n"
                f"⏰ Time: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                f"<b>Configuration:</b>\n"
                f"├ Max Requests: <code>{Config.MAX_REQUESTS:,}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"├ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n"
                f"└ Monitoring: <code>{'Active' if Config.MONITORING_MODE else 'Disabled'}</code>",
            )

            self.logger.info("Initialization complete!")
            return True

        except SessionExpired:
            self.logger.error("Session expired! Generate new session string.")
            return False

        except AuthKeyInvalid:
            self.logger.error("Invalid session string! Check your SESSION_STRING.")
            return False

        except Exception as e:
            self.logger.exception(f"Initialization error: {e}")
            return False

    # ---------------- RUN ---------------- #

    async def run(self):
        if not await self.initialize():
            return  # ❌ DO NOT use sys.exit inside async

        self._running = True

        try:
            if Config.MONITORING_MODE:
                self.logger.info("Starting VC monitoring...")
                self.monitor_task = asyncio.create_task(
                    self.vc_detector.monitor_loop(
                        self.bot_handler.notify_vc_detected
                    )
                )

            self.logger.info("Bot is running...")
            await idle()

        except (KeyboardInterrupt, asyncio.CancelledError):
            self.logger.info("Shutdown signal received")

        finally:
            await self.shutdown()

    # ---------------- SHUTDOWN ---------------- #

    async def shutdown(self):
        self.logger.info("Shutting down...")
        self._running = False

        # Cancel monitoring task
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        # Stop attack safely
        if self.attack_engine and getattr(self.attack_engine, "stats", None):
            if self.attack_engine.stats.is_running:
                self.attack_engine.stop_attack()

        # Stop VC detector
        if self.vc_detector:
            self.vc_detector.stop()

        # Stop clients safely
        try:
            if self.user_client and self.user_client.is_connected:
                await self.user_client.stop()
        except Exception as e:
            self.logger.error(f"User client stop error: {e}")

        try:
            if self.bot and self.bot.is_connected:
                await self.bot.stop()
        except Exception as e:
            self.logger.error(f"Bot client stop error: {e}")

        self.logger.info("Shutdown complete.")


# ---------------- ENTRY POINT ---------------- #

async def main():
    manager = BotManager()
    await manager.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Bot stopped by user")
    except Exception as e:
        print(f"\n[!] Fatal error: {e}")
        sys.exit(1)
