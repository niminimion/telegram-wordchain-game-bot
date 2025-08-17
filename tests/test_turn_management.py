"""
Unit tests for turn management and player queue functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from bot.models import GameState, Player, GameConfig


class TestTurnManagement:
    """Test cases for turn management functionality."""
    
    @pytest.fixture
    def game_config(self):
        """Create a test game configuration."""
        return GameConfig(
            turn_timeout=30,
            min_word_length=1,
            max_players_per_game=5
        )
    
    @pytest.fixture
    def test_players(self):
        """Create test players."""
        return [
            Player(user_id=1, username="player1", first_name="Alice"),
            Player(user_id=2, username="player2", first_name="Bob"),
            Player(user_id=3, username="player3", first_name="Charlie"),
            Player(user_id=4, username="player4", first_name="Diana")
        ]
    
    @pytest.fixture
    def game_state(self, test_players, game_config):
        """Create a test game state."""
        return GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=test_players.copy(),
            game_config=game_config
        )
    
    def test_get_current_player(self, game_state, test_players):
        """Test getting the current player."""
        # Should return first player initially
        current = game_state.get_current_player()
        assert current == test_players[0]
        
        # Change index and test again
        game_state.current_player_index = 2
        current = game_state.get_current_player()
        assert current == test_players[2]
    
    def test_get_current_player_empty_game(self, game_config):
        """Test getting current player when no players exist."""
        empty_game = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=[],
            game_config=game_config
        )
        
        assert empty_game.get_current_player() is None
    
    def test_advance_turn(self, game_state, test_players):
        """Test advancing to the next player's turn."""
        initial_time = game_state.turn_start_time
        
        # Advance turn
        game_state.advance_turn()
        
        # Should move to next player
        assert game_state.current_player_index == 1
        assert game_state.get_current_player() == test_players[1]
        
        # Turn start time should be updated
        assert game_state.turn_start_time != initial_time
        assert game_state.turn_start_time is not None
    
    def test_advance_turn_wraps_around(self, game_state, test_players):
        """Test that advancing turn wraps around to first player."""
        # Set to last player
        game_state.current_player_index = len(test_players) - 1
        
        # Advance turn
        game_state.advance_turn()
        
        # Should wrap to first player
        assert game_state.current_player_index == 0
        assert game_state.get_current_player() == test_players[0]
    
    def test_get_next_player(self, game_state, test_players):
        """Test getting next player without advancing."""
        # Should return second player
        next_player = game_state.get_next_player()
        assert next_player == test_players[1]
        
        # Current player should not change
        assert game_state.current_player_index == 0
        assert game_state.get_current_player() == test_players[0]
    
    def test_get_next_player_wraps_around(self, game_state, test_players):
        """Test that get_next_player wraps around."""
        # Set to last player
        game_state.current_player_index = len(test_players) - 1
        
        # Next player should be first
        next_player = game_state.get_next_player()
        assert next_player == test_players[0]
    
    def test_get_player_turn_order(self, game_state, test_players):
        """Test getting players in turn order."""
        # From first player
        turn_order = game_state.get_player_turn_order()
        assert turn_order == test_players
        
        # From third player
        game_state.current_player_index = 2
        turn_order = game_state.get_player_turn_order()
        expected = test_players[2:] + test_players[:2]
        assert turn_order == expected
    
    def test_add_player_success(self, game_state, game_config):
        """Test successfully adding a player to the game."""
        new_player = Player(user_id=5, username="player5", first_name="Eve")
        
        result = game_state.add_player(new_player)
        
        assert result == True
        assert new_player in game_state.players
        assert len(game_state.players) == 5
    
    def test_add_duplicate_player(self, game_state, test_players):
        """Test adding a player that already exists."""
        # Try to add existing player
        result = game_state.add_player(test_players[0])
        
        assert result == False
        assert len(game_state.players) == 4  # Should not change
    
    def test_add_player_exceeds_limit(self, game_state, game_config):
        """Test adding player when at maximum capacity."""
        # Add one more player to reach limit (5)
        new_player = Player(user_id=5, username="player5", first_name="Eve")
        game_state.add_player(new_player)
        
        # Try to add another (should fail)
        another_player = Player(user_id=6, username="player6", first_name="Frank")
        result = game_state.add_player(another_player)
        
        assert result == False
        assert len(game_state.players) == 5
    
    def test_remove_player_success(self, game_state, test_players):
        """Test successfully removing a player."""
        result = game_state.remove_player(test_players[1].user_id)
        
        assert result == True
        assert test_players[1] not in game_state.players
        assert len(game_state.players) == 3
    
    def test_remove_nonexistent_player(self, game_state):
        """Test removing a player that doesn't exist."""
        result = game_state.remove_player(999)  # Non-existent user ID
        
        assert result == False
        assert len(game_state.players) == 4  # Should not change
    
    def test_remove_current_player_adjusts_index(self, game_state, test_players):
        """Test that removing current player adjusts the index correctly."""
        # Set current player to index 2
        game_state.current_player_index = 2
        current_player = game_state.get_current_player()
        
        # Remove the current player
        game_state.remove_player(current_player.user_id)
        
        # Index should be adjusted (wrapped to 0 since we removed player at index 2)
        assert game_state.current_player_index == 0
        assert len(game_state.players) == 3
    
    def test_remove_player_before_current_adjusts_index(self, game_state, test_players):
        """Test that removing player before current adjusts index."""
        # Set current player to index 2
        game_state.current_player_index = 2
        
        # Remove player at index 0 (before current)
        game_state.remove_player(test_players[0].user_id)
        
        # Current index should be decremented
        assert game_state.current_player_index == 1
        assert game_state.get_current_player() == test_players[2]  # Same player, new index
    
    def test_should_end_game_conditions(self, game_state, test_players):
        """Test game end conditions."""
        # With 4 active players, game should continue
        assert game_state.should_end_game() == False
        
        # Remove players until only 1 remains
        game_state.remove_player(test_players[0].user_id)
        game_state.remove_player(test_players[1].user_id)
        game_state.remove_player(test_players[2].user_id)
        
        # With 1 player, game should end
        assert game_state.should_end_game() == True
        
        # With 0 players, game should end
        game_state.remove_player(test_players[3].user_id)
        assert game_state.should_end_game() == True
    
    def test_get_active_players(self, game_state, test_players):
        """Test getting only active players."""
        # All players active initially
        active = game_state.get_active_players()
        assert len(active) == 4
        assert all(p.is_active for p in active)
        
        # Deactivate one player
        test_players[1].is_active = False
        active = game_state.get_active_players()
        assert len(active) == 3
        assert test_players[1] not in active
    
    def test_set_player_active_status(self, game_state, test_players):
        """Test setting player active status."""
        # Deactivate a player
        result = game_state.set_player_active_status(test_players[1].user_id, False)
        
        assert result == True
        assert test_players[1].is_active == False
        
        # Reactivate the player
        result = game_state.set_player_active_status(test_players[1].user_id, True)
        
        assert result == True
        assert test_players[1].is_active == True
    
    def test_set_active_status_nonexistent_player(self, game_state):
        """Test setting active status for non-existent player."""
        result = game_state.set_player_active_status(999, False)
        
        assert result == False
    
    def test_skip_inactive_players(self, game_state, test_players):
        """Test skipping to next active player."""
        # Deactivate current player (index 0)
        test_players[0].is_active = False
        
        # Skip inactive players
        game_state.skip_inactive_players()
        
        # Should advance to next active player (index 1)
        assert game_state.current_player_index == 1
        assert game_state.get_current_player() == test_players[1]
        assert game_state.get_current_player().is_active == True
    
    def test_skip_multiple_inactive_players(self, game_state, test_players):
        """Test skipping multiple consecutive inactive players."""
        # Deactivate first two players
        test_players[0].is_active = False
        test_players[1].is_active = False
        
        # Skip inactive players
        game_state.skip_inactive_players()
        
        # Should advance to first active player (index 2)
        assert game_state.current_player_index == 2
        assert game_state.get_current_player() == test_players[2]
        assert game_state.get_current_player().is_active == True
    
    def test_deactivate_current_player_auto_skips(self, game_state, test_players):
        """Test that deactivating current player automatically skips."""
        # Current player is at index 0
        assert game_state.current_player_index == 0
        
        # Deactivate current player
        game_state.set_player_active_status(test_players[0].user_id, False)
        
        # Should automatically skip to next active player
        assert game_state.current_player_index == 1
        assert game_state.get_current_player() == test_players[1]
    
    def test_turn_timing_functions(self, game_state):
        """Test turn timing calculation functions."""
        # Mock current time
        start_time = datetime.now()
        game_state.turn_start_time = start_time
        
        with patch('bot.models.datetime') as mock_datetime:
            # Mock 15 seconds elapsed
            mock_datetime.now.return_value = start_time + timedelta(seconds=15)
            
            # Test duration calculation
            duration = game_state.get_turn_duration()
            assert duration == 15.0
            
            # Test remaining time calculation (30s timeout - 15s elapsed = 15s remaining)
            remaining = game_state.get_remaining_turn_time()
            assert remaining == 15.0
    
    def test_turn_timing_no_start_time(self, game_state):
        """Test turn timing when no start time is set."""
        game_state.turn_start_time = None
        
        assert game_state.get_turn_duration() is None
        assert game_state.get_remaining_turn_time() is None
    
    def test_remaining_time_never_negative(self, game_state):
        """Test that remaining time never goes negative."""
        start_time = datetime.now()
        game_state.turn_start_time = start_time
        
        with patch('bot.models.datetime') as mock_datetime:
            # Mock 45 seconds elapsed (more than 30s timeout)
            mock_datetime.now.return_value = start_time + timedelta(seconds=45)
            
            remaining = game_state.get_remaining_turn_time()
            assert remaining == 0.0  # Should not be negative


if __name__ == "__main__":
    pytest.main([__file__])