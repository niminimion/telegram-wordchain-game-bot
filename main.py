#!/usr/bin/env python3
"""
Telegram Word Game Bot
A bot that manages turn-based word games in Telegram group chats.

This is the main entry point for the bot. It initializes all components,
starts the Telegram bot, and handles graceful shutdown.
"""

import asyncio
import logging
import sys
import signal
import os
from datetime import datetime
from pathlib import Path

from bot.config import config
from bot.models import GameConfig
from bot.word_validators import create_word_validator
from bot.game_manager import GameManager
from bot.telegram_bot import create_telegram_bot
from bot.error_handler import error_handler

# Version information
__version__ = "1.0.0"
__author__ = "Telegram Word Game Bot"

# Global instances for cleanup
bot_instance = None
game_manager = None
application = None
shutdown_event = asyncio.Event()


def setup_logging():
    """Configure comprehensive logging."""
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler for all logs
    try:
        file_handler = logging.FileHandler(
            log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log"
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not setup file logging: {e}")
    
    return logging.getLogger(__name__)


async def health_check():
    """Perform system health check."""
    logger = logging.getLogger(__name__)
    
    try:
        # Check configuration
        config.validate()
        
        # Check word validator
        word_validator = create_word_validator(config.wordnik_api_key)
        validator_available = await word_validator.is_service_available()
        
        # Check system resources
        if game_manager:
            stats = game_manager.get_concurrent_stats()
            resource_status = stats['resource_status']
        else:
            resource_status = "unknown"
        
        health_status = {
            'timestamp': datetime.now().isoformat(),
            'config_valid': True,
            'word_validator_available': validator_available,
            'resource_status': resource_status,
            'version': __version__
        }
        
        logger.info(f"Health check: {health_status}")
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'timestamp': datetime.now().isoformat(),
            'status': 'unhealthy',
            'error': str(e),
            'version': __version__
        }


async def graceful_shutdown():
    """Handle graceful shutdown of all components."""
    global bot_instance, game_manager, application
    
    logger = logging.getLogger(__name__)
    logger.info("Initiating graceful shutdown...")
    
    shutdown_tasks = []
    
    try:
        # Stop Telegram bot
        if bot_instance:
            logger.info("Shutting down Telegram bot...")
            shutdown_tasks.append(bot_instance.shutdown())
        
        # Stop Telegram application
        if application:
            logger.info("Stopping Telegram application...")
            try:
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
            except Exception as e:
                logger.error(f"Error stopping Telegram application: {e}")
        
        # Stop concurrent monitoring
        if game_manager:
            logger.info("Stopping concurrent game monitoring...")
            shutdown_tasks.append(game_manager.stop_concurrent_monitoring())
        
        # Wait for all shutdown tasks
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        
        # Final error summary
        error_handler.log_error_summary(24)
        
        logger.info("Graceful shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")
    
    finally:
        # Set shutdown event
        shutdown_event.set()


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, initiating shutdown...")
    
    # Create shutdown task
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(graceful_shutdown())
    else:
        asyncio.run(graceful_shutdown())


async def periodic_maintenance():
    """Perform periodic maintenance tasks."""
    logger = logging.getLogger(__name__)
    
    error_report_interval = 3600  # 1 hour
    health_check_interval = 1800  # 30 minutes
    
    last_error_report = 0
    last_health_check = 0
    
    while not shutdown_event.is_set():
        try:
            current_time = asyncio.get_event_loop().time()
            
            # Periodic error summary and system status
            if current_time - last_error_report >= error_report_interval:
                error_handler.log_error_summary(24)
                
                if game_manager:
                    stats = game_manager.get_concurrent_stats()
                    logger.info(f"System Status: {stats['resource_status']}, "
                               f"Games: {stats['active_games']}/{stats['max_games']}, "
                               f"Players: {stats['total_players']}")
                
                last_error_report = current_time
            
            # Periodic health check
            if current_time - last_health_check >= health_check_interval:
                await health_check()
                last_health_check = current_time
            
            # Wait before next check
            await asyncio.sleep(60)  # Check every minute
            
        except asyncio.CancelledError:
            logger.info("Periodic maintenance cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic maintenance: {e}")
            await asyncio.sleep(60)  # Continue after error


async def initialize_components():
    """Initialize all bot components."""
    global game_manager, bot_instance, application
    
    logger = logging.getLogger(__name__)
    
    # Validate configuration
    logger.info("Validating configuration...")
    config.validate()
    logger.info("✅ Configuration validated successfully")
    
    # Create game configuration
    game_config = GameConfig.from_env()
    logger.info(f"✅ Game config loaded: timeout={game_config.turn_timeout}s, "
               f"max_players={game_config.max_players_per_game}")
    
    # Create word validator
    logger.info("Initializing word validator...")
    word_validator = create_word_validator(config.wordnik_api_key)
    
    # Test validator availability
    validator_available = await word_validator.is_service_available()
    if validator_available:
        logger.info("✅ Word validator is available")
    else:
        logger.warning("⚠️ Word validator may have limited functionality")
    
    # Create game manager
    logger.info("Creating game manager...")
    game_manager = GameManager(word_validator, game_config)
    logger.info("✅ Game manager created")
    
    # Start concurrent game monitoring
    logger.info("Starting concurrent game monitoring...")
    await game_manager.start_concurrent_monitoring()
    logger.info("✅ Concurrent game monitoring started")
    
    # Create and setup Telegram bot
    logger.info("Setting up Telegram bot...")
    bot_instance = create_telegram_bot(game_manager)
    application = bot_instance.setup_application()
    logger.info("✅ Telegram bot configured")
    
    # Initialize Telegram application
    logger.info("Initializing Telegram application...")
    await application.initialize()
    await application.start()
    logger.info("✅ Telegram application initialized")
    
    return application


async def main():
    """Main entry point for the Telegram Word Game Bot."""
    # Setup logging first
    logger = setup_logging()
    
    # Log startup information
    logger.info("="*60)
    logger.info(f"Starting Telegram Word Game Bot v{__version__}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Log level: {config.log_level}")
    logger.info("="*60)
    
    try:
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize all components
        application = await initialize_components()
        
        # Start bot polling
        logger.info("Starting bot polling...")
        await application.updater.start_polling()
        logger.info("🚀 Bot is running! Press Ctrl+C to stop.")
        
        # Start periodic maintenance
        maintenance_task = asyncio.create_task(periodic_maintenance())
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
        # Cancel maintenance task
        maintenance_task.cancel()
        try:
            await maintenance_task
        except asyncio.CancelledError:
            pass
        
        logger.info("Bot stopped gracefully")
        
    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        logger.error("Please check your .env file and ensure all required variables are set")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error during startup: {e}")
        logger.exception("Full traceback:")
        sys.exit(1)


if __name__ == '__main__':
    try:
        # Check Python version
        if sys.version_info < (3, 10):
            print("❌ Python 3.10 or higher is required")
            sys.exit(1)
        
        # Run the bot
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot crashed: {e}")
        sys.exit(1)
