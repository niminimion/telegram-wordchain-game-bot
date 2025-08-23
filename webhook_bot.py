#!/usr/bin/env python3
"""
Webhook-enabled Telegram Word Game Bot for Render deployment.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import Update
import threading

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Global bot components
bot_application = None
bot_instance = None

async def initialize_bot():
    """Initialize the bot components."""
    global bot_application, bot_instance
    
    try:
        logger.info("🚀 Initializing Telegram Word Game Bot...")
        
        # Import components
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
        bot_instance = create_telegram_bot(game_manager)
        bot_application = bot_instance.setup_application()
        
        # Initialize the application
        await bot_application.initialize()
        await bot_application.start()
        
        # Set webhook URL
        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/{os.getenv('TELEGRAM_BOT_TOKEN')}"
        await bot_application.bot.set_webhook(url=webhook_url)
        
        logger.info(f"🎉 Bot initialized! Webhook URL: {webhook_url}")
        
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        import traceback
        traceback.print_exc()
        raise

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render."""
    return jsonify({
        'status': 'healthy',
        'bot_initialized': bot_application is not None
    })

@app.route(f"/{os.getenv('TELEGRAM_BOT_TOKEN')}", methods=['POST'])
def webhook():
    """Handle incoming webhook updates from Telegram."""
    try:
        if not bot_application:
            logger.error("Bot not initialized")
            return "Bot not ready", 503
        
        # Get the update from Telegram
        update_data = request.get_json(force=True)
        update = Update.de_json(update_data, bot_application.bot)
        
        # Process the update asynchronously
        asyncio.create_task(bot_application.process_update(update))
        
        return "OK"
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return "Error", 500

@app.route('/', methods=['GET'])
def root():
    """Root endpoint."""
    return jsonify({
        'message': 'Telegram Word Game Bot is running!',
        'status': 'active'
    })

def run_bot_initialization():
    """Run bot initialization in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(initialize_bot())
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    # Initialize bot in a separate thread
    bot_thread = threading.Thread(target=run_bot_initialization)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Wait for bot to initialize
    import time
    time.sleep(5)
    
    # Start Flask app
    port = int(os.getenv('PORT', 10000))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)