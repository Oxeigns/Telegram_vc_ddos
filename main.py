"""
Main Entry Point - Simplified
Only Bot, no User Session needed
"""

import asyncio
import logging
import sys
from pyrogram import Client, idle

from config import Config
from attack_engine import AttackEngine
from bot_handler import BotHandler


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
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
        if not Config.validate():
            return False
        
        try:
            # Attack Engine
            self.logger.info("Initializing Attack Engine...")
            self.engine = AttackEngine(
                max_requests=Config.MAX_REQUESTS,
                thread_count=Config.THREAD_COUNT,
                timeout=Config.ATTACK_TIMEOUT
            )
            
            # Bot Client (Only Bot Token - no session string!)
            self.logger.info("Starting Bot...")
            self.bot = Client(
                "stress_bot",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=Config.BOT_TOKEN,
                workers=4
            )
            
            await self.bot.start()
            
            # Bot Handler
            self.handler = BotHandler(
                bot=self.bot,
                attack_engine=self.engine,
                admin_id=Config.ADMIN_USER_ID
            )
            
            # Startup message
            try:
                await self.bot.send_message(
                    Config.ADMIN_USER_ID,
                    "🤖 <b>Bot Started!</b>\n\n"
                    "Send /start to open Control Panel",
                    parse_mode="html"
                )
            except Exception as e:
                self.logger.error(f"Startup message failed: {e}")
            
            self.logger.info("Bot is running!")
            return True
            
        except Exception as e:
            self.logger.exception(f"Init error: {e}")
            return False
    
    async def run(self):
        if not await self.initialize():
            return
        
        try:
            await idle()
        except KeyboardInterrupt:
            self.logger.info("Stopped by user")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        self.logger.info("Shutting down...")
        if self.engine and self.engine.stats.is_running:
            self.engine.stop_attack()
        if self.bot:
            await self.bot.stop()
        self.logger.info("Done!")


def main():
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
        print("\n[*] Stopped")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
