#!/usr/bin/env python3
"""
Minimal bot for testing basic functionality.
"""

import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Simple game state
games = {}

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new word game."""
    chat_id = update.effective_chat.id
    
    if chat_id in games:
        await update.message.reply_text("A game is already running! Use /stopgame to end it.")
        return
    
    # Start a simple game
    games[chat_id] = {
        'current_letter': 'A',
        'players': [],
        'active': True
    }
    
    await update.message.reply_text(
        f"🎮 Word Game Started!\n\n"
        f"Current letter: {games[chat_id]['current_letter']}\n"
        f"Send a word that starts with this letter!"
    )

async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the current game."""
    chat_id = update.effective_chat.id
    
    if chat_id not in games:
        await update.message.reply_text("No game is currently running.")
        return
    
    del games[chat_id]
    await update.message.reply_text("Game stopped!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show game status."""
    chat_id = update.effective_chat.id
    
    if chat_id not in games:
        await update.message.reply_text("No game is currently running. Use /startgame to start!")
        return
    
    game = games[chat_id]
    await update.message.reply_text(
        f"Game Status:\n"
        f"Current letter: {game['current_letter']}\n"
        f"Players: {len(game['players'])}\n"
        f"Active: {game['active']}"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle word submissions."""
    chat_id = update.effective_chat.id
    
    if chat_id not in games:
        return
    
    word = update.message.text.strip().upper()
    game = games[chat_id]
    
    if word.startswith(game['current_letter']) and word.isalpha():
        # Simple validation - just check if it starts with the right letter
        # Update to next letter
        next_letter = chr(ord(game['current_letter']) + 1)
        if next_letter > 'Z':
            next_letter = 'A'
        
        game['current_letter'] = next_letter
        
        await update.message.reply_text(
            f"✅ Good word: {word}!\n"
            f"Next letter: {next_letter}"
        )
    else:
        await update.message.reply_text(
            f"❌ Invalid word. Must start with {game['current_letter']} and contain only letters."
        )

def main():
    """Main bot function."""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        return
    
    logger.info("Starting minimal word game bot...")
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("startgame", start_game))
    application.add_handler(CommandHandler("stopgame", stop_game))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    logger.info("Bot is running! Add it to a group and use /startgame")
    logger.info("Press Ctrl+C to stop")
    application.run_polling()

if __name__ == "__main__":
    main()