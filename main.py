"""
VC Monitor Bot - Main Entry Point
Production-ready deployment for Heroku
"""

import asyncio
import logging
import sys
import os
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
    
    # Reduce noise from pyrogram
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("pyrogram.session").setLevel(logging.ERROR)
    
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
        self._shutdown_event = asyncio.Event()
        self._initialized = False

    # ---------------- INITIALIZE ---------------- #

    async def initialize(self) -> bool:
        """Initialize all components with error handling"""
        self.logger.info("=" * 50)
        self.logger.info("VC Monitor Bot - Starting Initialization")
        self.logger.info(f"Time: {datetime.now().isoformat()}")
        
        try:
            server_ip = get_public_ip()
            self.logger.info(f"Server IP: {server_ip}")
        except Exception as e:
            self.logger.warning(f"Could not get server IP: {e}")
            server_ip = "unknown"
            
        self.logger.info("=" * 50)

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
                takeout=False,
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

            # Initialize VC Detector
            self.logger.info("Initializing VC Detector...")
            self.vc_detector = VoiceChatDetector(
                user_client=self.user_client,
                admin_id=Config.ADMIN_USER_ID,
                check_interval=Config.VC_CHECK_INTERVAL,
            )

            # Start clients with retry logic
            self.logger.info("Starting User Client...")
            await self._start_client_with_retry(self.user_client, "User Client")
            
            self.logger.info("Starting Bot Client...")
            await self._start_client_with_retry(self.bot, "Bot Client")

            # Initialize bot handlers
            self.logger.info("Registering Bot Handlers...")
            self.bot_handler = BotHandler(
                bot=self.bot,
                attack_engine=self.attack_engine,
                admin_id=Config.ADMIN_USER_ID,
            )

            # Send startup notification
            try:
                await self.bot.send_message(
                    Config.ADMIN_USER_ID,
                    f"🤖 <b>Bot Started Successfully</b>\n\n"
                    f"🌐 Server IP: <code>{server_ip}</code>\n"
                    f"⏰ Time: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                    f"<b>Configuration:</b>\n"
                    f"├ Max Requests: <code>{Config.MAX_REQUESTS:,}</code>\n"
                    f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                    f"├ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n"
                    f"└ Monitoring: <code>{'Active' if Config.MONITORING_MODE else 'Disabled'}</code>",
                )
            except Exception as e:
                self.logger.error(f"Failed to send startup message: {e}")

            self._initialized = True
            self.logger.info("Initialization complete!")
            return True

        except SessionExpired:
            self.logger.error("Session expired! Generate new session string.")
            return False

        except AuthKeyInvalid:
            self.logger.error("Invalid session string! Check your SESSION_STRING.")
            return False
            
        except ConnectionError as e:
            self.logger.error(f"Connection error: {e}")
            return False

        except Exception as e:
            self.logger.exception(f"Initialization error: {e}")
            return False
    
    async def _start_client_with_retry(self, client: Client, name: str, max_retries: int = 3):
        """Start client with retry logic"""
        for attempt in range(max_retries):
            try:
                await client.start()
                self.logger.info(f"{name} started successfully")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"{name} start failed (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise

    # ---------------- RUN ---------------- #

    async def run(self):
        """Main run loop with proper signal handling"""
        if not await self.initialize():
            return

        try:
            if Config.MONITORING_MODE:
                self.logger.info("Starting VC monitoring...")
                self.monitor_task = asyncio.create_task(
                    self._monitor_wrapper(),
                    name="vc_monitor"
                )

            self.logger.info("Bot is running. Press Ctrl+C to stop.")
            
            # Use idle() for graceful shutdown
            await idle()
            
        except asyncio.CancelledError:
            self.logger.info("Run cancelled")
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.exception(f"Run error: {e}")
        finally:
            await self.shutdown()
    
    async def _monitor_wrapper(self):
        """Wrapper for monitor loop with error handling"""
        try:
            await self.vc_detector.monitor_loop(
                self.bot_handler.notify_vc_detected
            )
        except asyncio.CancelledError:
            self.logger.info("Monitor task cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Monitor error: {e}")
            # Try to notify admin
            try:
                await self.bot.send_message(
                    Config.ADMIN_USER_ID,
                    f"⚠️ Monitor error: {str(e)[:100]}"
                )
            except:
                pass

    # ---------------- SHUTDOWN ---------------- #

    async def shutdown(self):
        """Graceful shutdown with proper cleanup"""
        if not self._initialized:
            return
            
        self.logger.info("Shutting down...")
        self._shutdown_event.set()

        # Cancel monitor task gracefully
        if self.monitor_task and not self.monitor_task.done():
            self.logger.info("Cancelling monitor task...")
            self.monitor_task.cancel()
            try:
                await asyncio.wait_for(self.monitor_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        # Stop attack engine
        if self.attack_engine:
            try:
                if hasattr(self.attack_engine, 'stats') and self.attack_engine.stats.is_running:
                    self.logger.info("Stopping active attack...")
                    self.attack_engine.stop_attack()
                    await asyncio.sleep(1)  # Give threads time to stop
            except Exception as e:
                self.logger.error(f"Attack engine stop error: {e}")

        # Stop VC detector
        if self.vc_detector:
            try:
                self.vc_detector.stop()
            except Exception as e:
                self.logger.error(f"VC detector stop error: {e}")

        # Stop clients gracefully
        await self._stop_client(self.user_client, "User Client")
        await self._stop_client(self.bot, "Bot Client")

        self.logger.info("Shutdown complete.")
    
    async def _stop_client(self, client: Optional[Client], name: str):
        """Safely stop a client"""
        if not client:
            return
            
        try:
            # Check if client has session attribute (means it was started)
            if hasattr(client, 'session') and client.session:
                self.logger.info(f"Stopping {name}...")
                await client.stop()
                self.logger.info(f"{name} stopped")
        except Exception as e:
            self.logger.error(f"{name} stop error: {e}")


# ---------------- ENTRY POINT ---------------- #

def main():
    """Synchronous entry point"""
    # Windows specific: Use SelectorEventLoopPolicy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Get or create event loop
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
        # Clean up any remaining tasks
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        
        # Close loop gracefully
        try:
            if not loop.is_closed():
                loop.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
