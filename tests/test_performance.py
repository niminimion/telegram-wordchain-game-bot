"""
Performance tests for the Telegram Word Game Bot.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock
from concurrent.futures import ThreadPoolExecutor

from bot.word_validators import create_word_validator
from bot.game_manager import GameManager
from bot.timer_manager import GameTimerManager
from bot.models import Player, GameConfig
from bot.concurrent_manager import create_concurrent_manager


class TestGameManagerPerformance:
    """Performance tests for GameManager."""
    
    @pytest.fixture
    async def game_manager(self):
        """Create GameManager for performance testing."""
        word_validator = create_word_validator()
        game_config = GameConfig()
        manager = GameManager(word_validator, game_config)
        
        await manager.start_concurrent_monitoring()
        
        yield manager
        
        await manager.stop_concurrent_monitoring()
    
    @pytest.mark.asyncio
    async def test_concurrent_game_creation_performance(self, game_manager):
        """Test performance of creating multiple games concurrently."""
        num_games = 50
        players_per_game = 3
        
        async def create_game(game_id):
            chat_id = 10000 + game_id
            players = [
                Player(user_id=game_id*10+i, username=f"user{game_id}_{i}", first_name=f"User{game_id}_{i}")
                for i in range(players_per_game)
            ]
            
            start_time = time.time()
            game_state = await game_manager.start_game(chat_id, players)
            end_time = time.time()
            
            return end_time - start_time, game_state is not None
        
        # Create games concurrently
        start_total = time.time()
        tasks = [create_game(i) for i in range(num_games)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_total = time.time()
        
        # Analyze results
        successful_games = 0
        total_creation_time = 0
        
        for result in results:
            if isinstance(result, tuple):
                creation_time, success = result
                if success:
                    successful_games += 1
                    total_creation_time += creation_time
        
        # Performance assertions
        total_time = end_total - start_total
        avg_creation_time = total_creation_time / successful_games if successful_games > 0 else 0
        
        print(f"\nGame Creation Performance:")
        print(f"  Total games attempted: {num_games}")
        print(f"  Successful games: {successful_games}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Average creation time: {avg_creation_time:.4f}s")
        print(f"  Games per second: {successful_games / total_time:.2f}")
        
        # Performance requirements
        assert successful_games >= num_games * 0.8  # At least 80% success rate
        assert avg_creation_time < 0.1  # Less than 100ms per game
        assert total_time < 10.0  # Complete within 10 seconds
        
        # Cleanup
        stats = game_manager.get_concurrent_stats()
        active_games = stats['active_games']
        
        cleanup_start = time.time()
        for i in range(active_games):
            chat_id = 10000 + i
            await game_manager.stop_game(chat_id)
        cleanup_end = time.time()
        
        print(f"  Cleanup time: {cleanup_end - cleanup_start:.2f}s")
    
    @pytest.mark.asyncio
    async def test_word_processing_performance(self, game_manager):
        """Test performance of word processing."""
        chat_id = 12345
        players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=2, username="bob", first_name="Bob")
        ]
        
        # Start game
        game_state = await game_manager.start_game(chat_id, players)
        
        # Mock word validation for consistent timing
        with patch.object(game_manager.word_validator, 'validate_word', return_value=True):
            num_words = 100
            processing_times = []
            
            for i in range(num_words):
                current_state = game_manager.get_game_status(chat_id)
                if not current_state:
                    break
                
                current_player = current_state.get_current_player()
                if not current_player:
                    break
                
                # Create a valid word
                letter = current_state.current_letter.lower()
                word = f"{letter}{'a' * (current_state.required_length - 1)}"
                
                start_time = time.time()
                result, error = await game_manager.process_word(chat_id, current_player.user_id, word)
                end_time = time.time()
                
                processing_times.append(end_time - start_time)
                
                # Stop if word length gets too long (avoid infinite growth)
                if current_state.required_length > 10:
                    break
        
        # Analyze performance
        if processing_times:
            avg_time = sum(processing_times) / len(processing_times)
            max_time = max(processing_times)
            min_time = min(processing_times)
            
            print(f"\nWord Processing Performance:")
            print(f"  Words processed: {len(processing_times)}")
            print(f"  Average time: {avg_time:.4f}s")
            print(f"  Min time: {min_time:.4f}s")
            print(f"  Max time: {max_time:.4f}s")
            print(f"  Words per second: {1/avg_time:.2f}")
            
            # Performance requirements
            assert avg_time < 0.05  # Less than 50ms average
            assert max_time < 0.2   # Less than 200ms maximum
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_concurrent_word_processing(self, game_manager):
        """Test concurrent word processing across multiple games."""
        num_games = 10
        words_per_game = 5
        
        # Create multiple games
        games = {}
        for i in range(num_games):
            chat_id = 20000 + i
            players = [Player(user_id=i*10+1, username=f"user{i}", first_name=f"User{i}")]
            game_state = await game_manager.start_game(chat_id, players)
            games[chat_id] = game_state
        
        # Process words concurrently
        with patch.object(game_manager.word_validator, 'validate_word', return_value=True):
            async def process_words_for_game(chat_id, game_state):
                times = []
                for j in range(words_per_game):
                    current_state = game_manager.get_game_status(chat_id)
                    if not current_state or not current_state.is_active:
                        break
                    
                    player = current_state.get_current_player()
                    if not player:
                        break
                    
                    letter = current_state.current_letter.lower()
                    word = f"{letter}{'a' * (current_state.required_length - 1)}"
                    
                    start_time = time.time()
                    result, error = await game_manager.process_word(chat_id, player.user_id, word)
                    end_time = time.time()
                    
                    times.append(end_time - start_time)
                    
                    if current_state.required_length > 8:  # Prevent excessive length
                        break
                
                return times
            
            start_total = time.time()
            tasks = [process_words_for_game(chat_id, game_state) for chat_id, game_state in games.items()]
            results = await asyncio.gather(*tasks)
            end_total = time.time()
            
            # Analyze results
            all_times = []
            for game_times in results:
                all_times.extend(game_times)
            
            if all_times:
                total_time = end_total - start_total
                avg_time = sum(all_times) / len(all_times)
                
                print(f"\nConcurrent Word Processing Performance:")
                print(f"  Games: {num_games}")
                print(f"  Total words processed: {len(all_times)}")
                print(f"  Total time: {total_time:.2f}s")
                print(f"  Average processing time: {avg_time:.4f}s")
                print(f"  Concurrent throughput: {len(all_times) / total_time:.2f} words/sec")
                
                # Performance requirements
                assert avg_time < 0.1  # Less than 100ms average
                assert len(all_times) / total_time > 20  # At least 20 words/sec throughput
        
        # Cleanup
        for chat_id in games.keys():
            await game_manager.stop_game(chat_id)


class TestTimerPerformance:
    """Performance tests for timer system."""
    
    @pytest.mark.asyncio
    async def test_timer_accuracy(self):
        """Test timer accuracy and performance."""
        from bot.timer_manager import TimerManager
        
        timer_manager = TimerManager()
        
        # Test multiple timers with different durations
        test_durations = [0.1, 0.2, 0.5, 1.0]  # seconds
        results = []
        
        for duration in test_durations:
            callback_times = []
            
            async def test_callback(chat_id):
                callback_times.append(time.time())
            
            # Start timer
            start_time = time.time()
            await timer_manager.start_turn_timer(
                chat_id=12345,
                timeout_seconds=duration,
                timeout_callback=test_callback
            )
            
            # Wait for callback
            await asyncio.sleep(duration + 0.1)  # Small buffer
            
            if callback_times:
                actual_duration = callback_times[0] - start_time
                accuracy = abs(actual_duration - duration) / duration
                results.append((duration, actual_duration, accuracy))
        
        # Analyze accuracy
        print(f"\nTimer Accuracy Performance:")
        for expected, actual, accuracy in results:
            print(f"  Expected: {expected:.1f}s, Actual: {actual:.3f}s, Accuracy: {(1-accuracy)*100:.1f}%")
        
        # Performance requirements
        for expected, actual, accuracy in results:
            assert accuracy < 0.1  # Less than 10% error
        
        # Cleanup
        await timer_manager.cancel_all_timers()
    
    @pytest.mark.asyncio
    async def test_concurrent_timers_performance(self):
        """Test performance with many concurrent timers."""
        from bot.timer_manager import TimerManager
        
        timer_manager = TimerManager()
        num_timers = 50
        
        callback_count = 0
        callback_times = []
        
        async def test_callback(chat_id):
            nonlocal callback_count
            callback_count += 1
            callback_times.append(time.time())
        
        # Start many timers
        start_time = time.time()
        for i in range(num_timers):
            await timer_manager.start_turn_timer(
                chat_id=10000 + i,
                timeout_seconds=0.5,  # All expire at roughly the same time
                timeout_callback=test_callback
            )
        
        creation_time = time.time() - start_time
        
        # Wait for all callbacks
        await asyncio.sleep(1.0)
        
        # Analyze performance
        print(f"\nConcurrent Timers Performance:")
        print(f"  Timers created: {num_timers}")
        print(f"  Creation time: {creation_time:.3f}s")
        print(f"  Callbacks received: {callback_count}")
        print(f"  Creation rate: {num_timers / creation_time:.1f} timers/sec")
        
        # Performance requirements
        assert creation_time < 1.0  # Create 50 timers in less than 1 second
        assert callback_count >= num_timers * 0.9  # At least 90% of callbacks
        
        # Cleanup
        await timer_manager.cancel_all_timers()


class TestConcurrentManagerPerformance:
    """Performance tests for concurrent game management."""
    
    @pytest.mark.asyncio
    async def test_resource_monitoring_performance(self):
        """Test performance of resource monitoring."""
        concurrent_manager = create_concurrent_manager(max_games=100)
        
        # Create many games for monitoring
        active_games = {}
        num_games = 50
        
        for i in range(num_games):
            chat_id = 30000 + i
            players = [Player(user_id=i*10+1, username=f"user{i}", first_name=f"User{i}")]
            
            from bot.models import GameState, GameConfig
            game_state = GameState(
                chat_id=chat_id,
                current_letter=chr(65 + (i % 26)),
                required_length=1,
                current_player_index=0,
                players=players,
                is_active=True,
                game_config=GameConfig()
            )
            
            active_games[chat_id] = game_state
            concurrent_manager.register_game_start(chat_id, game_state)
        
        # Test monitoring performance
        monitoring_times = []
        
        for _ in range(10):  # Multiple measurements
            start_time = time.time()
            status = concurrent_manager.get_system_status(active_games)
            end_time = time.time()
            
            monitoring_times.append(end_time - start_time)
        
        # Analyze performance
        avg_time = sum(monitoring_times) / len(monitoring_times)
        max_time = max(monitoring_times)
        
        print(f"\nResource Monitoring Performance:")
        print(f"  Games monitored: {num_games}")
        print(f"  Average monitoring time: {avg_time:.4f}s")
        print(f"  Max monitoring time: {max_time:.4f}s")
        print(f"  Monitoring rate: {1/avg_time:.1f} checks/sec")
        
        # Performance requirements
        assert avg_time < 0.01  # Less than 10ms average
        assert max_time < 0.05  # Less than 50ms maximum
        
        # Test metrics collection performance
        metrics_times = []
        
        for _ in range(10):
            start_time = time.time()
            all_metrics = concurrent_manager.get_game_metrics()
            end_time = time.time()
            
            metrics_times.append(end_time - start_time)
        
        avg_metrics_time = sum(metrics_times) / len(metrics_times)
        
        print(f"  Average metrics collection time: {avg_metrics_time:.4f}s")
        
        assert avg_metrics_time < 0.02  # Less than 20ms average
    
    @pytest.mark.asyncio
    async def test_cleanup_performance(self):
        """Test performance of game cleanup operations."""
        concurrent_manager = create_concurrent_manager(max_games=100)
        
        # Create mock game manager
        cleanup_count = 0
        
        class MockGameManager:
            async def stop_game(self, chat_id):
                nonlocal cleanup_count
                cleanup_count += 1
                await asyncio.sleep(0.001)  # Simulate small delay
        
        mock_game_manager = MockGameManager()
        
        # Create games and make them appear inactive
        active_games = {}
        num_games = 30
        
        for i in range(num_games):
            chat_id = 40000 + i
            players = [Player(user_id=i*10+1, username=f"user{i}", first_name=f"User{i}")]
            
            from bot.models import GameState, GameConfig
            from datetime import datetime, timedelta
            
            game_state = GameState(
                chat_id=chat_id,
                current_letter="A",
                required_length=1,
                current_player_index=0,
                players=players,
                is_active=True,
                game_config=GameConfig()
            )
            
            active_games[chat_id] = game_state
            concurrent_manager.register_game_start(chat_id, game_state)
            
            # Make games appear inactive
            concurrent_manager.resource_monitor.game_metrics[chat_id].last_activity = (
                datetime.now() - timedelta(hours=2)
            )
        
        # Test cleanup performance
        start_time = time.time()
        cleaned_count = await concurrent_manager.cleanup_inactive_games(active_games, mock_game_manager)
        end_time = time.time()
        
        cleanup_time = end_time - start_time
        
        print(f"\nCleanup Performance:")
        print(f"  Games to clean: {num_games}")
        print(f"  Games cleaned: {cleaned_count}")
        print(f"  Cleanup time: {cleanup_time:.3f}s")
        print(f"  Cleanup rate: {cleaned_count / cleanup_time:.1f} games/sec")
        
        # Performance requirements
        assert cleanup_time < 2.0  # Complete cleanup in less than 2 seconds
        assert cleaned_count == num_games  # All games should be cleaned
        assert cleanup_count == num_games  # All stop_game calls should be made


class TestMemoryPerformance:
    """Memory usage and leak tests."""
    
    @pytest.mark.asyncio
    async def test_memory_usage_stability(self):
        """Test that memory usage remains stable during operations."""
        import gc
        import sys
        
        # Force garbage collection
        gc.collect()
        
        # Get initial memory usage (rough estimate)
        initial_objects = len(gc.get_objects())
        
        # Create and destroy many games
        word_validator = create_word_validator()
        game_manager = GameManager(word_validator)
        
        num_cycles = 10
        games_per_cycle = 20
        
        for cycle in range(num_cycles):
            # Create games
            games = {}
            for i in range(games_per_cycle):
                chat_id = 50000 + cycle * 1000 + i
                players = [Player(user_id=i*10+1, username=f"user{i}", first_name=f"User{i}")]
                game_state = await game_manager.start_game(chat_id, players)
                games[chat_id] = game_state
            
            # Process some words
            with patch.object(game_manager.word_validator, 'validate_word', return_value=True):
                for chat_id, game_state in games.items():
                    player = game_state.get_current_player()
                    if player:
                        await game_manager.process_word(chat_id, player.user_id, "test")
            
            # Clean up games
            for chat_id in games.keys():
                await game_manager.stop_game(chat_id)
            
            # Force garbage collection
            gc.collect()
            
            # Check memory usage periodically
            if cycle % 5 == 0:
                current_objects = len(gc.get_objects())
                print(f"  Cycle {cycle}: {current_objects} objects ({current_objects - initial_objects:+d})")
        
        # Final memory check
        gc.collect()
        final_objects = len(gc.get_objects())
        memory_growth = final_objects - initial_objects
        
        print(f"\nMemory Usage Test:")
        print(f"  Initial objects: {initial_objects}")
        print(f"  Final objects: {final_objects}")
        print(f"  Memory growth: {memory_growth} objects")
        print(f"  Growth per cycle: {memory_growth / num_cycles:.1f} objects")
        
        # Memory requirements (allow some growth for caching, etc.)
        assert memory_growth < 1000  # Less than 1000 objects growth
        assert memory_growth / num_cycles < 50  # Less than 50 objects per cycle


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])