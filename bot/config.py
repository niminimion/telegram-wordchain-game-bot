"""
Configuration management for the Telegram Word Game Bot.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class BotConfig:
    """Bot configuration loaded from environment variables."""
    
    def __init__(self):
        self.telegram_bot_token = self._get_required_env('TELEGRAM_BOT_TOKEN')
        self.wordnik_api_key = os.getenv('WORDNIK_API_KEY')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.max_concurrent_games = int(os.getenv('MAX_GAMES', '100'))
    
    @staticmethod
    def _get_required_env(key: str) -> str:
        """Get a required environment variable or raise an error."""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    def validate(self) -> None:
        """Validate the configuration."""
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        
        if self.max_concurrent_games <= 0:
            raise ValueError("MAX_GAMES must be a positive integer")
        
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(valid_log_levels)}")


class GameConfig:
    """Game configuration loaded from environment variables."""
    
    def __init__(self):
        self.min_word_length = 2  # Changed from 1 to 2
        self.wordnik_api_key = os.getenv('WORDNIK_API_KEY')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.max_concurrent_games = int(os.getenv('MAX_GAMES', '100'))
    
    @staticmethod
    def _get_required_env(key: str) -> str:
        """Get a required environment variable or raise an error."""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    def validate(self) -> None:
        """Validate the configuration."""
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        
        if self.max_concurrent_games <= 0:
            raise ValueError("MAX_GAMES must be a positive integer")
        
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(valid_log_levels)}")


# Global configuration instance
config = BotConfig()