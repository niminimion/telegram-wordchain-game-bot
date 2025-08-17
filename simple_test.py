#!/usr/bin/env python3
"""
Simple test script to validate bot startup.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("🔧 Testing bot components...")

try:
    # Test basic imports
    print("📦 Testing imports...")
    from bot.config import BotConfig
    from bot.models import GameConfig
    from bot.validators import create_word_validator
    print("✅ Basic imports successful")
    
    # Test configuration
    print("⚙️  Testing configuration...")
    config = BotConfig()
    config.validate()
    print(f"✅ Configuration valid - Token: {config.telegram_bot_token[:10]}...")
    
    # Test game config
    print("🎮 Testing game configuration...")
    game_config = GameConfig.from_env()
    print(f"✅ Game config - Timeout: {game_config.turn_timeout}s, Max players: {game_config.max_players_per_game}")
    
    print("🎉 All basic tests passed! Bot is ready to start.")
    
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)