"""
Timer management system for turn timeouts in the Telegram Word Game Bot.
"""

import asyncio
import logging
from typing import Callable, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class TimerManager:
    """Manages turn timers using asyncio tasks."""
    
    def __init__(self):
        self._active_timers: Dict[int, asyncio.Task] = {}
    
    async def start_turn_timer(
        self,
        chat_id: int,
        timeout_seconds: int,
        timeout_callback: Callable[[int], Any],
        warning_callback: Optional[Callable[[int, int], Any]] = None,
        warning_times: Optional[list] = None
    ) -> asyncio.Task:
        """
        Start a turn timer for a specific chat.
        
        Args:
            chat_id: The chat ID for the game
            timeout_seconds: Total timeout duration in seconds
            timeout_callback: Function to call when timer expires
            warning_callback: Optional function to call for warnings
            warning_times: List of seconds before timeout to send warnings
        
        Returns:
            The asyncio Task managing the timer
        """
        # Cancel any existing timer for this chat
        await self.cancel_timer(chat_id)
        
        # Create and start new timer task
        timer_task = asyncio.create_task(
            self._timer_coroutine(
                chat_id, 
                timeout_seconds, 
                timeout_callback,
                warning_callback,
                warning_times or []
            )
        )
        
        self._active_timers[chat_id] = timer_task
        logger.debug(f"Started {timeout_seconds}s timer for chat {chat_id}")
        
        return timer_task
    
    async def cancel_timer(self, chat_id: int) -> bool:
        """
        Cancel the active timer for a chat.
        
        Args:
            chat_id: The chat ID
            
        Returns:
            True if a timer was cancelled, False if no timer was active
        """
        if chat_id in self._active_timers:
            timer_task = self._active_timers[chat_id]
            
            if not timer_task.done():
                timer_task.cancel()
                try:
                    await timer_task
                except asyncio.CancelledError:
                    pass
            
            del self._active_timers[chat_id]
            logger.debug(f"Cancelled timer for chat {chat_id}")
            return True
        
        return False
    
    def is_timer_active(self, chat_id: int) -> bool:
        """Check if a timer is currently active for a chat."""
        if chat_id not in self._active_timers:
            return False
        
        timer_task = self._active_timers[chat_id]
        return not timer_task.done()
    
    def get_active_timer_count(self) -> int:
        """Get the number of currently active timers."""
        return len([t for t in self._active_timers.values() if not t.done()])
    
    async def cleanup_completed_timers(self) -> None:
        """Remove completed timer tasks from tracking."""
        completed_chats = []
        
        for chat_id, timer_task in self._active_timers.items():
            if timer_task.done():
                completed_chats.append(chat_id)
        
        for chat_id in completed_chats:
            del self._active_timers[chat_id]
        
        if completed_chats:
            logger.debug(f"Cleaned up {len(completed_chats)} completed timers")
    
    async def cancel_all_timers(self) -> None:
        """Cancel all active timers."""
        chat_ids = list(self._active_timers.keys())
        
        for chat_id in chat_ids:
            await self.cancel_timer(chat_id)
        
        logger.info(f"Cancelled all {len(chat_ids)} active timers")
    
    async def _timer_coroutine(
        self,
        chat_id: int,
        timeout_seconds: int,
        timeout_callback: Callable[[int], Any],
        warning_callback: Optional[Callable[[int, int], Any]],
        warning_times: list
    ) -> None:
        """
        The main timer coroutine that handles warnings and timeout.
        
        Args:
            chat_id: The chat ID
            timeout_seconds: Total timeout duration
            timeout_callback: Function to call on timeout
            warning_callback: Function to call for warnings
            warning_times: List of warning times in seconds before timeout
        """
        try:
            start_time = datetime.now()
            elapsed = 0
            
            # Sort warning times in descending order
            warning_times_sorted = sorted(warning_times, reverse=True)
            warnings_sent = set()
            
            while elapsed < timeout_seconds:
                # Check for warnings
                if warning_callback:
                    for warning_time in warning_times_sorted:
                        remaining = timeout_seconds - elapsed
                        
                        if (remaining <= warning_time and 
                            warning_time not in warnings_sent and
                            remaining > 0):
                            
                            try:
                                # Call warning callback
                                if asyncio.iscoroutinefunction(warning_callback):
                                    await warning_callback(chat_id, remaining)
                                else:
                                    warning_callback(chat_id, remaining)
                                
                                warnings_sent.add(warning_time)
                                logger.debug(f"Sent {remaining}s warning for chat {chat_id}")
                                
                            except Exception as e:
                                logger.error(f"Error in warning callback for chat {chat_id}: {e}")
                
                # Sleep for 1 second
                await asyncio.sleep(1)
                
                # Update elapsed time
                elapsed = (datetime.now() - start_time).total_seconds()
            
            # Timer expired - call timeout callback
            try:
                if asyncio.iscoroutinefunction(timeout_callback):
                    await timeout_callback(chat_id)
                else:
                    timeout_callback(chat_id)
                
                logger.info(f"Timer expired for chat {chat_id} after {timeout_seconds}s")
                
            except Exception as e:
                logger.error(f"Error in timeout callback for chat {chat_id}: {e}")
        
        except asyncio.CancelledError:
            logger.debug(f"Timer cancelled for chat {chat_id}")
            raise
        
        except Exception as e:
            logger.error(f"Unexpected error in timer for chat {chat_id}: {e}")
        
        finally:
            # Clean up timer reference
            if chat_id in self._active_timers:
                del self._active_timers[chat_id]


class GameTimerManager:
    """High-level timer manager specifically for game turns."""
    
    def __init__(self, game_manager, announcement_callback=None):
        """
        Initialize the game timer manager.
        
        Args:
            game_manager: The GameManager instance
            announcement_callback: Optional callback for sending announcements
        """
        self.game_manager = game_manager
        self.announcement_callback = announcement_callback
        self.timer_manager = TimerManager()
    
    async def start_turn_timer(self, chat_id: int) -> bool:
        """
        Start a turn timer for the current player in a game.
        
        Args:
            chat_id: The chat ID for the game
            
        Returns:
            True if timer was started, False if no active game
        """
        game_state = self.game_manager.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return False
        
        # Cancel any existing timer
        if game_state.timer_task and not game_state.timer_task.done():
            game_state.timer_task.cancel()
        
        # Start new timer
        timer_task = await self.timer_manager.start_turn_timer(
            chat_id=chat_id,
            timeout_seconds=game_state.game_config.turn_timeout,
            timeout_callback=self._handle_timeout,
            warning_callback=self._handle_warning,
            warning_times=game_state.game_config.timeout_warnings
        )
        
        # Store timer task in game state
        game_state.timer_task = timer_task
        
        logger.info(f"Started turn timer for chat {chat_id}")
        return True
    
    async def cancel_turn_timer(self, chat_id: int) -> bool:
        """
        Cancel the turn timer for a game.
        
        Args:
            chat_id: The chat ID for the game
            
        Returns:
            True if timer was cancelled, False if no timer was active
        """
        # Cancel in timer manager
        cancelled = await self.timer_manager.cancel_timer(chat_id)
        
        # Clear timer task from game state
        game_state = self.game_manager.get_game_status(chat_id)
        if game_state:
            game_state.timer_task = None
        
        if cancelled:
            logger.info(f"Cancelled turn timer for chat {chat_id}")
        
        return cancelled
    
    async def _handle_timeout(self, chat_id: int) -> None:
        """Handle turn timeout - eliminate player."""
        try:
            # Get current player before timeout
            game_state = self.game_manager.get_game_status(chat_id)
            if not game_state or not game_state.is_active:
                return
            
            current_player = game_state.get_current_player()
            
            # Handle timeout in game manager (eliminates player)
            eliminated_player = await self.game_manager.handle_timeout(chat_id)
            
            # Send elimination announcement
            if self.announcement_callback and eliminated_player:
                try:
                    if asyncio.iscoroutinefunction(self.announcement_callback):
                        await self.announcement_callback(
                            chat_id, 
                            "player_eliminated", 
                            eliminated_player=eliminated_player,
                            reason="timeout"
                        )
                    else:
                        self.announcement_callback(
                            chat_id, 
                            "player_eliminated", 
                            eliminated_player=eliminated_player,
                            reason="timeout"
                        )
                except Exception as e:
                    logger.error(f"Error sending elimination announcement for chat {chat_id}: {e}")
            
            # Check if game ended (winner or no players left)
            updated_game_state = self.game_manager.get_game_status(chat_id)
            if updated_game_state and not updated_game_state.is_active:
                # Game ended
                winner = self.game_manager.get_winner(chat_id)
                if self.announcement_callback:
                    try:
                        if asyncio.iscoroutinefunction(self.announcement_callback):
                            await self.announcement_callback(
                                chat_id, 
                                "game_ended", 
                                winner=winner
                            )
                        else:
                            self.announcement_callback(
                                chat_id, 
                                "game_ended", 
                                winner=winner
                            )
                    except Exception as e:
                        logger.error(f"Error sending game end announcement for chat {chat_id}: {e}")
                
                # Clean up the game
                await self.game_manager.stop_game(chat_id)
            
            elif updated_game_state and updated_game_state.is_active:
                # Game continues with remaining players
                if self.announcement_callback:
                    try:
                        next_player = updated_game_state.get_current_player()
                        if asyncio.iscoroutinefunction(self.announcement_callback):
                            await self.announcement_callback(
                                chat_id, 
                                "next_turn", 
                                game_state=updated_game_state,
                                current_player=next_player
                            )
                        else:
                            self.announcement_callback(
                                chat_id, 
                                "next_turn", 
                                game_state=updated_game_state,
                                current_player=next_player
                            )
                    except Exception as e:
                        logger.error(f"Error sending next turn announcement for chat {chat_id}: {e}")
                
                # Start timer for next player
                await self.start_turn_timer(chat_id)
        
        except Exception as e:
            logger.error(f"Error handling timeout for chat {chat_id}: {e}")
    
    async def _handle_warning(self, chat_id: int, remaining_seconds: int) -> None:
        """Handle turn timeout warning."""
        try:
            if self.announcement_callback:
                game_state = self.game_manager.get_game_status(chat_id)
                if game_state and game_state.is_active:
                    current_player = game_state.get_current_player()
                    
                    if asyncio.iscoroutinefunction(self.announcement_callback):
                        await self.announcement_callback(
                            chat_id, 
                            "warning", 
                            current_player=current_player,
                            remaining_seconds=remaining_seconds
                        )
                    else:
                        self.announcement_callback(
                            chat_id, 
                            "warning", 
                            current_player=current_player,
                            remaining_seconds=remaining_seconds
                        )
        
        except Exception as e:
            logger.error(f"Error sending warning for chat {chat_id}: {e}")
    
    async def cleanup(self) -> None:
        """Clean up all timers."""
        await self.timer_manager.cancel_all_timers()
        logger.info("Game timer manager cleaned up")