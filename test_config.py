#!/usr/bin/env python3
"""
Test script to validate bot configuration.
"""

import sys
import os
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path.cwd()))

try:
    from bot.config import config
    print("✅ Configuration loaded successfully!")
    print(f"📱 Bot token: {config.telegram_bot_token[:10]}...")
    print(f"🔑 Wordnik API: {'Configured' if config.wordnik_api_key and config.wordnik_api_key != 'your_wordnik_api_key_here' else 'Not configured (using NLTK only)'}")
    print(f"📊 Log level: {config.log_level}")
    print(f"🎮 Max games: {config.max_concurrent_games}")
    
    # Test validation
    config.validate()
    print("✅ Configuration validation passed!")
    
except Exception as e:
    print(f"❌ Configuration error: {e}")
    sys.exit(1)