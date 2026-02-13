"""
VC Monitor Bot - Main Entry Point
Production-ready deployment for Heroku
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional

from pyrogram import Client, idle
from pyrogram.errors import SessionExpired, AuthKeyInvalid

from config import Config
from utils import get_public_ip
from attack_engine import AttackEngine
from vc_detector import VoiceChatDetector
from bot_handler import BotHandler


# ---------------- LOGGING SETUP ---------------- #

def setup_logging() -> logging.Logger:
    """Setup comprehensive logging"""
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
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
    """Main bot manager with proper lifecycle handling"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.user_client: Optional[Client] = None
        self.bot: Optional[Client] = None
        self.attack_engine: Optional[AttackEngine] = None
        self.vc_detector: Optional[VoiceChatDetector] = None
        self.bot_handler: Optional[BotHandler] = None
        self.monitor_task: Optional[asyncio.Task] = None
        self._running = False

    async def initialize(self) -> bool:
        """Initialize all components"""
        self.logger.info("=" * 60)
        self.logger.info("VC Monitor Bot - Starting Initialization")
        self.logger.info(f"Time: {datetime.now().isoformat()}")
        
        try:
            server_ip = get_public_ip()
            self.logger.info(f"Server IP: {server_ip}")
        except Exception as e:
            self.logger.warning(f"Could not get server IP: {e}")
            server_ip = "unknown"
            
        self.logger.info("=" * 60)

        if not Config.validate():
            self.logger.error("Configuration validation failed!")
            return False

        try:
            # Initialize User Client (for VC detection)
            self.logger.info("Initializing User Client...")
            self.user_client = Client(
                "user_session",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                session_string=Config.SESSION_STRING,
                no_updates=False,
            )

            # Initialize Bot Client
            self.logger.info("Initializing Bot Client...")
            self.bot = Client(
                "bot",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=Config.BOT_TOKEN,
                workers=4,
                parse_mode="html",
            )

            # Initialize Attack Engine
            self.logger.info("Initializing Attack Engine...")
            self.attack_engine = AttackEngine(
                max_requests=Config.MAX_REQUESTS,
                thread_count=Config.THREAD_COUNT,
                timeout=Config.ATTACK_TIMEOUT,
            )

            # Initialize VC Detector (before bot handler)
            self.logger.info("Initializing VC Detector...")
            self.vc_detector = VoiceChatDetector(
                user_client=self.user_client,
                admin_id=Config.ADMIN_USER_ID,
                check_interval=Config.VC_CHECK_INTERVAL,
            )

            # Start User Client
            self.logger.info("Starting User Client...")
            await self.user_client.start()
            self.logger.info("User Client connected!")

            # Start Bot Client
            self.logger.info("Starting Bot Client...")
            await self.bot.start()
            self.logger.info("Bot Client connected!")

            # Initialize Bot Handler with vc_detector
            self.logger.info("Registering Bot Handlers...")
            self.bot_handler = BotHandler(
                bot=self.bot,
                attack_engine=self.attack_engine,
                admin_id=Config.ADMIN_USER_ID,
                vc_detector=self.vc_detector,  # Pass vc_detector for invite link processing
            )

            # Send startup notification
            try:
                await self.bot.send_message(
                    Config.ADMIN_USER_ID,
                    f"🤖 <b>Bot Started Successfully</b>\n\n"
                    f"🌐 Server IP: <code>{server_ip}</code>\n"
                    f"⏰ Time: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                    f"<b>Features:</b>\n"
                    f"• Auto VC Detection\n"
                    f"• Manual Target via Invite Link\n"
                    f"• Fixed Request Limits\n\n"
                    f"<b>Config:</b>\n"
                    f"├ Max Requests: <code>{Config.MAX_REQUESTS:,}</code>\n"
                    f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                    f"└ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n\n"
                    f"Bot is ready!"
                )
            except Exception as e:
                self.logger.error(f"Failed to send startup message: {e}")

            self._running = True
            self.logger.info("Initialization complete!")
            return True

        except SessionExpired:
            self.logger.error("Session expired! Generate new session string.")
            return False
        except AuthKeyInvalid:
            self.logger.error("Invalid session string!")
            return False
        except Exception as e:
            self.logger.exception(f"Initialization error: {e}")
            return False

    async def run(self):
        """Main run loop"""
        if not await self.initialize():
            return

        try:
            if Config.MONITORING_MODE:
                self.logger.info("Starting VC monitoring...")
                self.monitor_task = asyncio.create_task(
                    self.vc_detector.monitor_loop(self.bot_handler.notify_vc_detected)
                )

            self.logger.info("Bot is running. Press Ctrl+C to stop.")
            await idle()
            
        except asyncio.CancelledError:
            self.logger.info("Run cancelled")
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.exception(f"Run error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("Shutting down...")
        self._running = False

        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        if self.attack_engine and hasattr(self.attack_engine, 'stats'):
            if self.attack_engine.stats.is_running:
                self.attack_engine.stop_attack()

        if self.vc_detector:
            self.vc_detector.stop()

        try:
            if self.user_client:
                await self.user_client.stop()
        except Exception as e:
            self.logger.error(f"User client stop error: {e}")

        try:
            if self.bot:
                await self.bot.stop()
        except Exception as e:
            self.logger.error(f"Bot client stop error: {e}")

        self.logger.info("Shutdown complete.")


# ---------------- ENTRY POINT ---------------- #

def main():
    """Synchronous entry point"""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    manager = BotManager()
    
    try:
        loop.run_until_complete(manager.run())
    except KeyboardInterrupt:
        print("\n[*] Bot stopped by user")
    except Exception as e:
        print(f"\n[!] Fatal error: {e}")
        sys.exit(1)
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        
        try:
            if not loop.is_closed():
                loop.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
