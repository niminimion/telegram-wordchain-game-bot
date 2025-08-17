"""
Example demonstrating concurrent game management and resource monitoring.
"""

import asyncio
import logging
from unittest.mock import AsyncMock

from bot.concurrent_manager import create_concurrent_manager, ChatIsolationManager
from bot.models import Player, GameState, GameConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demonstrate_concurrent_game_management():
    """Demonstrate concurrent game management features."""
    logger.info("🎮 Demonstrating Concurrent Game Management\n")
    
    # Create concurrent manager with limits
    concurrent_manager = create_concurrent_manager(max_games=5, max_players_per_game=4)
    
    # Start monitoring
    await concurrent_manager.start_monitoring()
    
    # Simulate multiple games
    active_games = {}
    
    try:
        # Create several games
        for i in range(1, 4):
            chat_id = 10000 + i
            players = [
                Player(user_id=i*10+j, username=f"user{i}{j}", first_name=f"User{i}{j}")
                for j in range(1, 3)  # 2 players per game
            ]
            
            game_state = GameState(
                chat_id=chat_id,
                current_letter=chr(65 + i),  # A, B, C
                required_length=i,
                current_player_index=0,
                players=players,
                is_active=True,
                game_config=GameConfig()
            )
            
            # Check if we can create the game
            can_create, reason = concurrent_manager.can_create_game(active_games, len(players))
            
            if can_create:
                active_games[chat_id] = game_state
                concurrent_manager.register_game_start(chat_id, game_state)
                logger.info(f"✅ Created game {i} in chat {chat_id} with {len(players)} players")
            else:
                logger.warning(f"❌ Cannot create game {i}: {reason}")
        
        # Show system status
        logger.info("\n📊 System Status After Game Creation:")
        status = concurrent_manager.get_system_status(active_games)
        logger.info(f"Resource Status: {status['resource_status']}")
        logger.info(f"Active Games: {status['metrics']['active_games']}")
        logger.info(f"Total Players: {status['metrics']['total_players']}")
        logger.info(f"Memory Usage: {status['metrics']['memory_usage_mb']:.1f} MB")
        
        # Simulate game activity
        logger.info("\n🎯 Simulating Game Activity:")
        
        for chat_id, game_state in active_games.items():
            # Simulate word submissions
            concurrent_manager.register_game_activity(
                chat_id, game_state, 
                words_submitted=2, 
                timeouts=1, 
                errors=0
            )
            logger.info(f"📝 Registered activity for game in chat {chat_id}")
        
        # Show game metrics
        logger.info("\n📈 Individual Game Metrics:")
        for chat_id in active_games.keys():
            metrics = concurrent_manager.get_game_metrics(chat_id)
            logger.info(f"Chat {chat_id}: {metrics['words_submitted']} words, "
                       f"{metrics['timeouts']} timeouts, {metrics['player_count']} players")
        
        # Test resource limits
        logger.info("\n🚫 Testing Resource Limits:")
        
        # Try to create too many games
        for i in range(4, 8):  # This should exceed the limit
            chat_id = 10000 + i
            players = [Player(user_id=i*10+1, username=f"user{i}1", first_name=f"User{i}1")]
            
            can_create, reason = concurrent_manager.can_create_game(active_games, len(players))
            
            if can_create:
                game_state = GameState(
                    chat_id=chat_id,
                    current_letter=chr(65 + i),
                    required_length=1,
                    current_player_index=0,
                    players=players,
                    is_active=True,
                    game_config=GameConfig()
                )
                active_games[chat_id] = game_state
                concurrent_manager.register_game_start(chat_id, game_state)
                logger.info(f"✅ Created additional game {i} in chat {chat_id}")
            else:
                logger.warning(f"❌ Cannot create game {i}: {reason}")
        
        # Try to create game with too many players
        logger.info("\n👥 Testing Player Limits:")
        too_many_players = [
            Player(user_id=100+i, username=f"player{i}", first_name=f"Player{i}")
            for i in range(6)  # More than max_players_per_game (4)
        ]
        
        can_create, reason = concurrent_manager.can_create_game(active_games, len(too_many_players))
        logger.info(f"Can create game with {len(too_many_players)} players: {can_create}")
        if not can_create:
            logger.info(f"Reason: {reason}")
        
        # Show final system status
        logger.info("\n📊 Final System Status:")
        final_status = concurrent_manager.get_system_status(active_games)
        logger.info(f"Resource Status: {final_status['resource_status']}")
        logger.info(f"Active Games: {final_status['metrics']['active_games']}/{final_status['limits']['max_games']}")
        logger.info(f"Total Players: {final_status['metrics']['total_players']}")
        
        # Show resource warnings
        if final_status['warnings']:
            logger.info("⚠️ Resource Warnings:")
            for warning in final_status['warnings'][-3:]:  # Show last 3 warnings
                logger.info(f"  {warning}")
        
        # Simulate game cleanup
        logger.info("\n🧹 Simulating Game Cleanup:")
        games_to_end = list(active_games.keys())[:2]  # End first 2 games
        
        for chat_id in games_to_end:
            concurrent_manager.register_game_end(chat_id)
            del active_games[chat_id]
            logger.info(f"🏁 Ended game in chat {chat_id}")
        
        # Show status after cleanup
        cleanup_status = concurrent_manager.get_system_status(active_games)
        logger.info(f"After cleanup - Active Games: {cleanup_status['metrics']['active_games']}")
        
    finally:
        # Stop monitoring
        await concurrent_manager.stop_monitoring()


async def demonstrate_chat_isolation():
    """Demonstrate chat isolation management."""
    logger.info("\n🔒 Demonstrating Chat Isolation\n")
    
    isolation_manager = ChatIsolationManager()
    
    # Simulate concurrent operations on different chats
    async def chat_operation(chat_id: int, operation_name: str, delay: float):
        """Simulate a chat operation."""
        logger.info(f"🔄 Starting {operation_name} for chat {chat_id}")
        
        async def actual_operation():
            await asyncio.sleep(delay)
            return f"{operation_name} completed for chat {chat_id}"
        
        result = await isolation_manager.execute_with_chat_lock(chat_id, actual_operation)
        logger.info(f"✅ {result}")
        return result
    
    # Run operations concurrently
    tasks = [
        chat_operation(12345, "word_processing", 0.2),
        chat_operation(67890, "word_processing", 0.1),
        chat_operation(12345, "turn_advance", 0.3),  # Same chat - should wait
        chat_operation(67890, "game_status", 0.1),   # Different chat - should run concurrently
        chat_operation(11111, "start_game", 0.2),    # New chat
    ]
    
    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(*tasks)
    end_time = asyncio.get_event_loop().time()
    
    logger.info(f"\n⏱️ All operations completed in {end_time - start_time:.2f} seconds")
    logger.info(f"📊 Active chats: {isolation_manager.get_active_chats()}")
    
    # Test lock cleanup
    logger.info("\n🧹 Testing Lock Cleanup:")
    initial_locks = len(isolation_manager.chat_locks)
    cleaned = isolation_manager.cleanup_old_locks(hours=0)  # Clean all locks
    logger.info(f"Cleaned {cleaned} old locks (had {initial_locks} total)")


async def demonstrate_resource_monitoring():
    """Demonstrate resource monitoring features."""
    logger.info("\n📊 Demonstrating Resource Monitoring\n")
    
    from bot.concurrent_manager import ResourceMonitor
    
    monitor = ResourceMonitor(max_games=10, max_players_per_game=5)
    
    # Test resource status calculation
    logger.info("Resource Status at Different Load Levels:")
    test_loads = [1, 3, 6, 8, 9, 10]
    
    for load in test_loads:
        status = monitor.get_resource_status(load, load * 3)
        usage_percent = (load / 10) * 100
        logger.info(f"  {load}/10 games ({usage_percent:3.0f}%): {status.value}")
    
    # Test game creation validation
    logger.info("\nGame Creation Validation:")
    test_scenarios = [
        (5, 3, "Normal load"),
        (9, 2, "High load"),
        (10, 1, "At capacity"),
        (5, 8, "Too many players"),
    ]
    
    for active_games, players, description in test_scenarios:
        can_create, reason = monitor.can_create_game(active_games, players)
        status = "✅ Allowed" if can_create else f"❌ Blocked: {reason}"
        logger.info(f"  {description} ({active_games} games, {players} players): {status}")
    
    # Simulate game metrics tracking
    logger.info("\nGame Metrics Tracking:")
    
    # Create mock game states
    for i in range(3):
        chat_id = 20000 + i
        players = [Player(user_id=i*10+j, username=f"u{i}{j}", first_name=f"U{i}{j}") for j in range(2)]
        game_state = GameState(
            chat_id=chat_id,
            current_letter=chr(65 + i),
            required_length=i + 1,
            current_player_index=0,
            players=players,
            is_active=True,
            game_config=GameConfig()
        )
        
        monitor.update_game_metrics(chat_id, game_state, words_submitted=i+1, timeouts=i)
        logger.info(f"  Tracked metrics for game {i+1} (chat {chat_id})")
    
    # Show system metrics
    active_games_dict = {}  # Mock active games for metrics calculation
    system_metrics = monitor.get_system_metrics(active_games_dict)
    
    logger.info("\nSystem Metrics:")
    logger.info(f"  Total Games: {system_metrics.total_games}")
    logger.info(f"  Active Games: {system_metrics.active_games}")
    logger.info(f"  Uptime: {system_metrics.uptime_seconds:.1f} seconds")
    logger.info(f"  Memory Usage: {system_metrics.memory_usage_mb:.1f} MB")
    logger.info(f"  CPU Usage: {system_metrics.cpu_usage_percent:.1f}%")


async def main():
    """Run all concurrent game management demonstrations."""
    logger.info("🚀 Starting Concurrent Game Management Demonstrations\n")
    
    try:
        await demonstrate_concurrent_game_management()
        await demonstrate_chat_isolation()
        await demonstrate_resource_monitoring()
        
        logger.info("\n🎉 All demonstrations completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Demonstration failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())