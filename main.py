import asyncio
import logging
import sys
from pyrogram import Client, idle

# In imports ka hona zaroori hai
from config import Config
from attack_engine import AttackEngine
from bot_handler import BotHandler

def setup_logging():
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL, "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    return logging.getLogger("Main")

class BotManager:
    def __init__(self):
        self.logger = setup_logging()
        self.bot = None
        self.engine = None
        self.handler = None

    async def initialize(self) -> bool:
        # 1. Config Check
        if not Config.validate():
            self.logger.error("Config validation failed! Check your .env or config file.")
            return False
        
        try:
            # 2. Attack Engine Setup
            self.logger.info("Initializing Attack Engine...")
            self.engine = AttackEngine(
                max_requests=Config.MAX_REQUESTS,
                thread_count=Config.THREAD_COUNT,
                timeout=Config.ATTACK_TIMEOUT
            )
            
            # 3. Bot Client Setup
            self.logger.info("Starting Bot Client...")
            self.bot = Client(
                "stress_bot",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=Config.BOT_TOKEN,
                workers=10 # Workers badha diye taaki zyada users handle ho sakein
            )
            
            # 4. Bot Handler Registration
            # NOTE: Handler ko start() se pehle register karna behtar hota hai
            self.handler = BotHandler(
                bot=self.bot,
                attack_engine=self.engine,
                admin_id=Config.ADMIN_USER_ID
            )
            self.handler.register_handlers() # Yeh method aapke BotHandler mein hona chahiye

            await self.bot.start()
            
            # 5. Admin Notification
            try:
                await self.bot.send_message(
                    Config.ADMIN_USER_ID,
                    "🤖 <b>Bot Started Successfully!</b>\n\n"
                    "System: Operational\n"
                    "Engine: Ready",
                    parse_mode="html"
                )
            except Exception as e:
                self.logger.warning(f"Could not send startup message to Admin: {e}")
            
            self.logger.info("Bot is fully operational!")
            return True
            
        except Exception as e:
            self.logger.exception(f"Initialization failed: {e}")
            return False
    
    async def run(self):
        if not await self.initialize():
            return
        
        try:
            # idle() bot ko tab tak chalta rakhta hai jab tak aap Ctrl+C nahi dabate
            await idle()
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        self.logger.info("Shutting down gracefully...")
        # Attack ko pehle stop karein
        if self.engine and hasattr(self.engine, 'stop_attack'):
            self.engine.stop_attack()
        
        if self.bot:
            await self.bot.stop()
        self.logger.info("Shutdown complete.")

async def main():
    # Windows fix for Asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    manager = BotManager()
    await manager.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass # User ne manually band kiya
