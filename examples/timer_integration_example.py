"""
Example demonstrating timer integration with the game system.
"""

import asyncio
import logging
from bot.game_manager import GameManager
from bot.timer_manager import GameTimerManager
from bot.validators import create_word_validator
from bot.models import Player, GameConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def announcement_callback(chat_id, event_type, **kwargs):
    """Example announcement callback for timer events."""
    if event_type == "timeout":
        current_player = kwargs.get('current_player')
        next_player = kwargs.get('next_player')
        logger.info(f"⏰ Time's up for {current_player}! Next turn: {next_player}")
    
    elif event_type == "warning":
        current_player = kwargs.get('current_player')
        remaining = kwargs.get('remaining_seconds')
        logger.info(f"⚠️ {current_player}, you have {remaining} seconds left!")


async def main():
    """Demonstrate timer integration."""
    # Create components
    word_validator = create_word_validator()
    game_config = GameConfig(turn_timeout=10, timeout_warnings=[5, 2])  # Short timeout for demo
    game_manager = GameManager(word_validator, game_config)
    
    # Create timer manager with announcement callback
    timer_manager = GameTimerManager(game_manager, announcement_callback)
    
    # Create test players
    players = [
        Player(user_id=1, username="alice", first_name="Alice"),
        Player(user_id=2, username="bob", first_name="Bob")
    ]
    
    chat_id = 12345
    
    try:
        # Start a game
        logger.info("Starting game...")
        game_state = await game_manager.start_game(chat_id, players)
        logger.info(f"Game started! Current letter: {game_state.current_letter}, "
                   f"Current player: {game_state.get_current_player()}")
        
        # Start turn timer
        logger.info("Starting turn timer...")
        await timer_manager.start_turn_timer(chat_id)
        
        # Simulate waiting for player input (timer will expire)
        logger.info("Waiting for timer to expire...")
        await asyncio.sleep(12)  # Wait longer than timeout
        
        # Check game state after timeout
        updated_state = game_manager.get_game_status(chat_id)
        if updated_state:
            logger.info(f"After timeout - Current player: {updated_state.get_current_player()}")
        
        # Simulate a valid word submission
        logger.info("Simulating word submission...")
        current_player = updated_state.get_current_player()
        if current_player:
            # Cancel current timer
            await timer_manager.cancel_turn_timer(chat_id)
            
            # Process word (this would normally come from Telegram)
            word = f"{updated_state.current_letter.lower()}at"
            result = await game_manager.process_word(chat_id, current_player.user_id, word)
            logger.info(f"Word '{word}' result: {result}")
            
            # Start timer for next turn
            if result.value == "valid":
                await timer_manager.start_turn_timer(chat_id)
                logger.info("Started timer for next turn")
                
                # Wait a bit more
                await asyncio.sleep(3)
    
    except Exception as e:
        logger.error(f"Error in demo: {e}")
    
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        await timer_manager.cleanup()
        await game_manager.stop_game(chat_id)
        logger.info("Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())