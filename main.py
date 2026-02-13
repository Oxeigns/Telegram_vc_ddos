"""
Main Entry Point - Optimized for Termux 24/7
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Load .env file if exists
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value.strip('"\'')

from pyrogram import Client, idle

from config import Config
from attack_engine import AttackEngine
from bot_handler import BotHandler


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("bot.log", encoding='utf-8')
        ]
    )
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    return logging.getLogger(__name__)


class BotManager:
    def __init__(self):
        self.logger = setup_logging()
        self.bot: Client = None
        self.engine: AttackEngine = None
        self.handler: BotHandler = None
    
    async def initialize(self) -> bool:
        self.logger.info("=" * 50)
        self.logger.info("🚀 Starting Bot Manager")
        self.logger.info("=" * 50)
        
        if not Config.validate():
            self.logger.error("❌ Configuration validation failed!")
            self.logger.error("Check your .env file")
            return False
        
        try:
            # Attack Engine
            self.logger.info("⚙️ Initializing Attack Engine...")
            self.engine = AttackEngine(
                max_requests=Config.MAX_REQUESTS,
                thread_count=Config.THREAD_COUNT,
                timeout=Config.ATTACK_TIMEOUT
            )
            self.logger.info(f"✅ Attack Engine ready (Threads: {Config.THREAD_COUNT})")
            
            # Bot Client
            self.logger.info("🤖 Starting Telegram Bot...")
            self.bot = Client(
                "termux_bot",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=Config.BOT_TOKEN,
                workers=4,
                parse_mode="html"
            )
            
            await self.bot.start()
            bot_info = await self.bot.get_me()
            self.logger.info(f"✅ Bot started: @{bot_info.username}")
            
            # Bot Handler
            self.logger.info("📝 Registering handlers...")
            self.handler = BotHandler(
                bot=self.bot,
                attack_engine=self.engine,
                admin_id=Config.ADMIN_USER_ID
            )
            self.logger.info("✅ Handlers registered")
            
            # Startup notification
            try:
                await self.bot.send_message(
                    Config.ADMIN_USER_ID,
                    "🤖 <b>Bot Started Successfully!</b>\n\n"
                    f"📱 <b>Platform:</b> Termux\n"
                    f"⚡ <b>Threads:</b> <code>{Config.THREAD_COUNT}</code>\n"
                    f"🔢 <b>Max Requests:</b> <code>{Config.MAX_REQUESTS:,}</code>\n\n"
                    "Send /start to open Control Panel",
                    parse_mode="html"
                )
            except Exception as e:
                self.logger.warning(f"Could not send startup message: {e}")
            
            self.logger.info("=" * 50)
            self.logger.info("✅ Bot is running 24/7!")
            self.logger.info("=" * 50)
            return True
            
        except Exception as e:
            self.logger.exception(f"❌ Initialization error: {e}")
            return False
    
    async def run(self):
        if not await self.initialize():
            return 1
        
        try:
            await idle()
        except KeyboardInterrupt:
            self.logger.info("⛔ Stopped by user")
        except Exception as e:
            self.logger.exception(f"❌ Runtime error: {e}")
            return 1
        finally:
            await self.shutdown()
        
        return 0
    
    async def shutdown(self):
        self.logger.info("🛑 Shutting down...")
        
        if self.engine and self.engine.stats.is_running:
            self.logger.info("Stopping active attack...")
            self.engine.stop_attack()
        
        if self.bot:
            try:
                await self.bot.send_message(
                    Config.ADMIN_USER_ID,
                    "🛑 <b>Bot Shutting Down</b>",
                    parse_mode="html"
                )
            except:
                pass
            await self.bot.stop()
        
        self.logger.info("✅ Shutdown complete")


def main():
    # Termux specific: Set event loop policy
    if sys.platform == "linux":
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except ImportError:
            pass
    
    # Get or create event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    manager = BotManager()
    
    try:
        exit_code = loop.run_until_complete(manager.run())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[*] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[*] Fatal error: {e}")
        sys.exit(1)
    finally:
        loop.close()


if __name__ == "__main__":
    main()
