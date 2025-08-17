#!/usr/bin/env python3
"""
Simple test script to verify the bug fixes are working correctly.
"""

import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.game_manager import GameManager
from bot.models import Player, GameConfig
from bot.word_validators import create_word_validator


async def test_minimum_players_fix():
    """Test that games require at least 2 players to start."""
    print("Testing minimum players requirement...")
    
    # Create game manager
    validator = create_word_validator()
    config = GameConfig(turn_timeout=30, min_word_length=3, max_word_length=20, max_players_per_game=5)
    game_manager = GameManager(validator, config)
    
    # Create a single player
    player1 = Player(user_id=1, username="player1", first_name="Alice")
    
    try:
        # Create a waiting game with 1 player
        await game_manager.create_waiting_game(1, player1)
        
        # Try to start the game with only 1 player - this should fail
        await game_manager.start_actual_game(1)
        print("❌ FAILED: Game started with only 1 player (should require 2)")
        return False
    except ValueError as e:
        if "at least 2 players" in str(e):
            print("✅ PASSED: Game correctly requires at least 2 players")
            return True
        else:
            print(f"❌ FAILED: Wrong error message: {e}")
            return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")
        return False


async def test_two_players_success():
    """Test that games can start with 2 players."""
    print("Testing game start with 2 players...")
    
    # Create game manager
    validator = create_word_validator()
    config = GameConfig(turn_timeout=30, min_word_length=3, max_word_length=20, max_players_per_game=5)
    game_manager = GameManager(validator, config)
    
    # Create two players
    player1 = Player(user_id=1, username="player1", first_name="Alice")
    player2 = Player(user_id=2, username="player2", first_name="Bob")
    
    try:
        # Create a waiting game with first player
        await game_manager.create_waiting_game(2, player1)
        
        # Add second player
        success = await game_manager.add_player_to_game(2, player2)
        if not success:
            print("❌ FAILED: Could not add second player")
            return False
        
        # Try to start the game with 2 players - this should succeed
        game_state = await game_manager.start_actual_game(2)
        if game_state and len(game_state.players) == 2:
            print("✅ PASSED: Game successfully started with 2 players")
            return True
        else:
            print("❌ FAILED: Game state is invalid")
            return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")
        return False


async def main():
    """Run all bug fix tests."""
    print("Running bug fix verification tests...\n")
    
    tests = [
        test_minimum_players_fix,
        test_two_players_success
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    print(f"Summary: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All bug fixes are working correctly!")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the fixes.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)