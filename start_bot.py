#!/usr/bin/env python3
"""
Direct bot startup script that bypasses complex imports.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def main():
    """Main bot startup function."""
    try:
        logger.info("🚀 Starting Telegram Word Game Bot...")
        
        # Import components directly
        from bot.config import BotConfig
        from bot.models import GameConfig
        from bot.validators import create_word_validator
        from bot.game_manager import GameManager
        from bot.telegram_bot import create_telegram_bot
        
        # Create configuration
        config = BotConfig()
        config.validate()
        logger.info(f"✅ Configuration loaded - Token: {config.telegram_bot_token[:10]}...")
        
        # Create game configuration
        game_config = GameConfig.from_env()
        logger.info(f"🎮 Game config - Timeout: {game_config.turn_timeout}s")
        
        # Create word validator
        logger.info("🔍 Initializing word validator...")
        word_validator = create_word_validator(config.wordnik_api_key)
        
        # Test validator
        validator_available = await word_validator.is_service_available()
        logger.info(f"✅ Word validator available: {validator_available}")
        
        # Create game manager
        logger.info("🎮 Creating game manager...")
        game_manager = GameManager(word_validator, game_config)
        
        # Create Telegram bot
        logger.info("🤖 Setting up Telegram bot...")
        bot = create_telegram_bot(game_manager)
        application = bot.setup_application()
        
        # Start the bot
        logger.info("🚀 Starting bot...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        logger.info("🎉 Bot is running! Send /startgame in a Telegram group to begin!")
        logger.info("Press Ctrl+C to stop the bot")
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Shutdown requested...")
        
    except Exception as e:
        logger.error(f"❌ Bot startup failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Cleanup
        try:
            if 'application' in locals():
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
            logger.info("✅ Bot shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))