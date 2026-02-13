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


# Configure logging
def setup_logging():
    """Setup comprehensive logging"""
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(Config.LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Reduce noise from pyrogram
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


class BotManager:
    """Main bot manager coordinating all components"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.user_client: Client = None
        self.bot: Client = None
        self.attack_engine: AttackEngine = None
        self.vc_detector: VoiceChatDetector = None
        self.bot_handler: BotHandler = None
        self._running = False
    
    async def initialize(self) -> bool:
        """Initialize all components"""
        self.logger.info("=" * 50)
        self.logger.info("VC Monitor Bot - Starting Initialization")
        self.logger.info(f"Time: {datetime.now().isoformat()}")
        self.logger.info(f"Server IP: {get_public_ip()}")
        self.logger.info("=" * 50)
        
        # Validate configuration
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
                no_updates=False  # Need updates for VC detection
            )
            
            # Initialize Bot Client
            self.logger.info("Initializing Bot Client...")
            self.bot = Client(
                "bot",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=Config.BOT_TOKEN,
                workers=4,
                parse_mode="html"
            )
            
            # Initialize Attack Engine
            self.logger.info("Initializing Attack Engine...")
            self.attack_engine = AttackEngine(
                max_requests=Config.MAX_REQUESTS,
                thread_count=Config.THREAD_COUNT,
                timeout=Config.ATTACK_TIMEOUT
            )
            
            # Initialize VC Detector
            self.logger.info("Initializing VC Detector...")
            self.vc_detector = VoiceChatDetector(
                user_client=self.user_client,
                admin_id=Config.ADMIN_USER_ID,
                check_interval=Config.VC_CHECK_INTERVAL
            )
            
            # Start clients
            self.logger.info("Starting User Client...")
            await self.user_client.start()
            
            self.logger.info("Starting Bot Client...")
            await self.bot.start()
            
            # Initialize bot handlers
            self.logger.info("Registering Bot Handlers...")
            self.bot_handler = BotHandler(
                bot=self.bot,
                attack_engine=self.attack_engine,
                admin_id=Config.ADMIN_USER_ID
            )
            
            # Send startup notification
            await self.bot.send_message(
                Config.ADMIN_USER_ID,
                f"🤖 <b>Bot Started Successfully</b>\n\n"
                f"🌐 Server IP: <code>{get_public_ip()}</code>\n"
                f"⏰ Time: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                f"<b>Configuration:</b>\n"
                f"├ Max Requests: <code>{Config.MAX_REQUESTS:,}</code>\n"
                f"├ Threads: <code>{Config.THREAD_COUNT}</code>\n"
                f"├ Timeout: <code>{Config.ATTACK_TIMEOUT}s</code>\n"
                f"└ Monitoring: <code>{'Active' if Config.MONITORING_MODE else 'Disabled'}</code>\n\n"
                f"Join a Voice Chat to begin!"
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
            self.logger.error(f"Initialization error: {e}", exc_info=True)
            return False
    
    async def run(self):
        """Main run loop"""
        if not await self.initialize():
            sys.exit(1)
        
        self._running = True
        
        try:
            # Start VC monitoring if enabled
            if Config.MONITORING_MODE:
                self.logger.info("Starting VC monitoring...")
                monitor_task = asyncio.create_task(
                    self.vc_detector.monitor_loop(
                        self.bot_handler.notify_vc_detected
                    )
                )
            
            # Keep running
            self.logger.info("Bot is running. Press Ctrl+C to stop.")
            await idle()
            
        except asyncio.CancelledError:
            self.logger.info("Received cancellation signal")
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("Shutting down...")
        self._running = False
        
        # Stop attack if running
        if self.attack_engine and self.attack_engine.stats.is_running:
            self.logger.info("Stopping active attack...")
            self.attack_engine.stop_attack()
        
        # Stop VC detector
        if self.vc_detector:
            self.vc_detector.stop()
        
        # Stop clients
        try:
            if self.user_client:
                await self.user_client.stop()
            if self.bot:
                await self.bot.stop()
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
        
        self.logger.info("Shutdown complete.")


async def main():
    """Entry point"""
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
