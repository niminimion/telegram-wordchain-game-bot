"""
Telegram bot handlers for the Word Game Bot.
"""

import logging
from typing import List, Optional
from telegram import Update, User
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

from .game_manager import GameManager
from .timer_manager import GameTimerManager
from .models import Player, GameResult
from .config import config
from .message_handler import create_message_handler
from .announcements import create_game_announcer
from .error_handler import error_handler, handle_error_decorator

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot handlers for the word game."""
    
    def __init__(self, game_manager: GameManager):
        self.game_manager = game_manager
        self.timer_manager = GameTimerManager(game_manager, self._send_announcement)
        self.message_handler = create_message_handler(game_manager, self.timer_manager)
        self.announcer = create_game_announcer(self._send_message_direct)
        self.application: Optional[Application] = None
    
    def setup_application(self) -> Application:
        """Set up the Telegram application with handlers."""
        # Create application
        self.application = Application.builder().token(config.telegram_bot_token).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("join", self.join_game_command))
        self.application.add_handler(CommandHandler("forcestart", self.force_start_command))
        self.application.add_handler(CommandHandler("stopgame", self.stop_game_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # Add message handler for word submissions
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        logger.info("Telegram bot application set up with handlers")
        return self.application
    
    @handle_error_decorator("join_game_command")
    async def join_game_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /join command - join or create a word game."""
        try:
            if not update.effective_chat or not update.effective_user:
                return
            
            chat_id = update.effective_chat.id
            user = update.effective_user
            
            # Check if this is a group chat
            if update.effective_chat.type == 'private':
                await update.message.reply_text(
                    "🎮 Word games can only be played in group chats! "
                    "Add me to a group and try again."
                )
                return
            
            # Check if game already exists
            existing_game = self.game_manager.get_game_status(chat_id)
            
            if existing_game:
                if existing_game.is_active and not existing_game.is_waiting_for_players:
                    # Game is already running
                    current_player = existing_game.get_current_player()
                    await update.message.reply_text(
                        f"🎮 A game is already in progress!\n\n"
                        f"📍 Current turn: {current_player}\n"
                        f"🔤 Letter: **{existing_game.current_letter}**\n"
                        f"📏 Length: **{existing_game.required_length}** letters\n\n"
                        f"Use /status for more details or /stopgame to end the current game.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                elif existing_game.is_waiting_for_players:
                    # Game is waiting for players, try to join
                    player = Player(
                        user_id=user.id,
                        username=user.username or "",
                        first_name=user.first_name
                    )
                    
                    if await self.game_manager.add_player_to_game(chat_id, player):
                        # Get updated game state to show correct player count
                        updated_game = self.game_manager.get_game_status(chat_id)
                        player_count = len(updated_game.players) if updated_game else 1
                        max_players = updated_game.game_config.max_players_per_game if updated_game else 10
                        
                        await update.message.reply_text(
                            f"✅ {user.first_name} joined the game!\n"
                            f"👥 Players: {player_count}/{max_players}\n\n"
                            f"Waiting for more players... Use /forcestart to begin immediately."
                        )
                        logger.info(f"Player {user.id} joined game in chat {chat_id}")
                    else:
                        await update.message.reply_text(
                            f"❌ Cannot join game. You might already be in the game or it's full."
                        )
                    return
            
            # Create new game
            player = Player(
                user_id=user.id,
                username=user.username or "",
                first_name=user.first_name
            )
            
            try:
                game_state = await self.game_manager.create_waiting_game(chat_id, player)
                
                await update.message.reply_text(
                    f"🎮 **Word Game Created!**\n\n"
                    f"👤 {user.first_name} started a new game!\n"
                    f"👥 Players: 1/{game_state.game_config.max_players_per_game}\n\n"
                    f"⏰ Waiting 60 seconds for more players to join...\n"
                    f"💬 Use /join to join the game\n"
                    f"⚡ Use /forcestart to begin immediately",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Start the 60-second waiting timer
                await self._start_waiting_timer(chat_id)
                
                logger.info(f"New game created in chat {chat_id} by user {user.id}")
                
            except ValueError as e:
                await update.message.reply_text(f"❌ Cannot create game: {e}")
            except Exception as e:
                logger.error(f"Error starting game: {e}")
                await update.message.reply_text(
                    "❌ An error occurred while starting the game. Please try again."
                )
        
        except Exception as e:
            logger.error(f"Error in join_game_command: {e}")
            import traceback
            traceback.print_exc()
            
            # Provide more specific error messages
            if "No waiting game found" in str(e):
                await update.message.reply_text("❌ No game found to join. Use /join to create a new game.")
            elif "Need at least 2 players" in str(e):
                await update.message.reply_text("❌ Cannot start game with less than 2 players.")
            elif "already be in the game" in str(e):
                await update.message.reply_text("❌ You are already in this game.")
            elif "full" in str(e).lower():
                await update.message.reply_text("❌ Game is full. Cannot join.")
            else:
                await update.message.reply_text(f"❌ Error joining game: {str(e)}")
    
    @handle_error_decorator("force_start_command")
    async def force_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /forcestart command - immediately start a waiting game."""
        try:
            if not update.effective_chat or not update.effective_user:
                return
            
            chat_id = update.effective_chat.id
            
            # Check if game exists and is waiting for players
            existing_game = self.game_manager.get_game_status(chat_id)
            if not existing_game:
                await update.message.reply_text(
                    "❌ No game found. Use /join to create a new game."
                )
                return
            
            if not existing_game.is_waiting_for_players:
                await update.message.reply_text(
                    "❌ Game is not in waiting phase. Use /join to create a new game or /status to check current game."
                )
                return
            
            if len(existing_game.players) < 2:
                await update.message.reply_text(
                    f"❌ Need at least 2 players to start the game.\n"
                    f"Current players: {len(existing_game.players)}\n"
                    f"Use /join to get more players!"
                )
                return
            
            # Force start the game
            await self._start_actual_game(chat_id)
            
            logger.info(f"Game force-started in chat {chat_id} by user {update.effective_user.id}")
            
        except Exception as e:
            logger.error(f"Error in force_start_command: {e}")
            await update.message.reply_text("❌ An unexpected error occurred.")
    
    async def _start_waiting_timer(self, chat_id: int) -> None:
        """Start the 60-second waiting timer with countdown announcements."""
        import asyncio
        
        async def waiting_countdown():
            try:
                # Wait 30 seconds, then announce 30 seconds left
                await asyncio.sleep(30)
                game_state = self.game_manager.get_game_status(chat_id)
                if game_state and game_state.is_waiting_for_players:
                    await self._send_message_direct(
                        chat_id,
                        f"⏰ **30 seconds left** to join the game!\n"
                        f"👥 Current players: {len(game_state.players)}\n"
                        f"Use /join to join or /forcestart to begin now!",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # Wait 10 more seconds, then announce 20 seconds left
                await asyncio.sleep(10)
                game_state = self.game_manager.get_game_status(chat_id)
                if game_state and game_state.is_waiting_for_players:
                    await self._send_message_direct(
                        chat_id,
                        f"⏰ **20 seconds left** to join!\n"
                        f"👥 Players: {len(game_state.players)}\n"
                        f"Use /join or /forcestart!",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # Wait 10 more seconds, then announce 10 seconds left
                await asyncio.sleep(10)
                game_state = self.game_manager.get_game_status(chat_id)
                if game_state and game_state.is_waiting_for_players:
                    await self._send_message_direct(
                        chat_id,
                        f"⏰ **10 seconds left!**\n"
                        f"👥 Players: {len(game_state.players)}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # Wait final 10 seconds, then start the game
                await asyncio.sleep(10)
                game_state = self.game_manager.get_game_status(chat_id)
                if game_state and game_state.is_waiting_for_players:
                    if len(game_state.players) >= 2:
                        await self._start_actual_game(chat_id)
                    elif len(game_state.players) == 1:
                        await self._send_message_direct(
                            chat_id,
                            "❌ Game cancelled - need at least 2 players to start.\n"
                            "Use /join to create a new game!"
                        )
                        await self.game_manager.stop_game(chat_id)
                    else:
                        await self._send_message_direct(
                            chat_id,
                            "❌ Game cancelled - no players joined."
                        )
                        await self.game_manager.stop_game(chat_id)
                        
            except Exception as e:
                logger.error(f"Error in waiting countdown: {e}")
        
        # Start the countdown task
        game_state = self.game_manager.get_game_status(chat_id)
        if game_state:
            game_state.waiting_timer_task = asyncio.create_task(waiting_countdown())
    
    async def _start_actual_game(self, chat_id: int) -> None:
        """Start the actual game after waiting period."""
        try:
            game_state = await self.game_manager.start_actual_game(chat_id)
            
            # Send game start announcement
            await self.announcer.announce_game_start(chat_id, game_state, include_rules=True)
            
            # Start turn timer
            await self.timer_manager.start_turn_timer(chat_id)
            
        except Exception as e:
            logger.error(f"Error starting actual game: {e}")
            await self._send_message_direct(
                chat_id,
                "❌ Error starting the game. Please try again."
            )
    
    async def stop_game_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stopgame command."""
        try:
            if not update.effective_chat:
                return
            
            chat_id = update.effective_chat.id
            
            # Stop the game
            success = await self.game_manager.stop_game(chat_id)
            
            if success:
                # Cancel timer
                await self.timer_manager.cancel_turn_timer(chat_id)
                
                # Send game end announcement
                await self.announcer.announce_game_end(chat_id, "stopped")
                logger.info(f"Game stopped in chat {chat_id} by user {update.effective_user.id}")
            else:
                await update.message.reply_text(
                    "🎮 No active game found in this chat.\n"
                    "Use /startgame to start a new game!"
                )
        
        except Exception as e:
            logger.error(f"Error in stop_game_command: {e}")
            await update.message.reply_text("❌ An error occurred while stopping the game.")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        try:
            if not update.effective_chat:
                return
            
            chat_id = update.effective_chat.id
            game_state = self.game_manager.get_game_status(chat_id)
            
            if not game_state or not game_state.is_active:
                await update.message.reply_text(
                    "🎮 **No Active Game**\n\n"
                    "There's no word game currently running in this chat.\n"
                    "Use /startgame to start a new game!"
                )
                return
            
            current_player = game_state.get_current_player()
            remaining_time = self.game_manager.get_turn_time_remaining(chat_id)
            
            # Format remaining time
            time_str = "⏰ Unknown"
            if remaining_time is not None:
                if remaining_time > 0:
                    time_str = f"⏰ {int(remaining_time)}s remaining"
                else:
                    time_str = "⏰ Time's up!"
            
            # Get player list
            player_list = "\n".join([
                f"{'👉 ' if p == current_player else '   '}{p}"
                for p in game_state.players
            ])
            
            await update.message.reply_text(
                f"🎮 **Game Status**\n\n"
                f"📍 **Current Turn:** {current_player}\n"
                f"🔤 **Letter:** {game_state.current_letter}\n"
                f"📏 **Length:** {game_state.required_length} letters\n"
                f"{time_str}\n\n"
                f"👥 **Players:**\n{player_list}\n\n"
                f"{self.game_manager.get_word_hints(chat_id)}\n"
                f"{self.game_manager.get_difficulty_assessment(chat_id)}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        except Exception as e:
            logger.error(f"Error in status_command: {e}")
            await update.message.reply_text("❌ An error occurred while getting game status.")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        try:
            help_text = (
                "🎮 **Word Game Bot Help**\n\n"
                "**Commands:**\n"
                "• `/join` - Join or create a new word game\n"
                "• `/forcestart` - Start game immediately (during waiting)\n"
                "• `/stopgame` - Stop the current game\n"
                "• `/status` - Show current game status\n"
                "• `/help` - Show this help message\n\n"
                "**How to Play:**\n"
                "1️⃣ Use `/join` to create/join a game\n"
                "2️⃣ Wait 60 seconds for others to join, or use `/forcestart`\n"
                "3️⃣ Take turns submitting words\n"
                "4️⃣ Words must start with the given letter\n"
                "5️⃣ Words must be at least the minimum length (longer is OK!)\n"
                "6️⃣ Minimum length increases every 2 complete rounds\n"
                "7️⃣ You have 30 seconds per turn\n"
                "8️⃣ Words must be valid English words\n\n"
                "**Example:**\n"
                "Letter: C, Min: 3 → \"cat\" or \"computer\" ✅\n"
                "Next: Letter: T, Min: 3 → \"tree\" ✅\n\n"
                "**New Features:**\n"
                "• 60-second waiting period with countdown\n"
                "• Words can exceed minimum length\n"
                "• Length increases only after 2 full rounds\n"
                "• Wrong words don't affect next letter\n\n"
                "Have fun! 🎯"
            )
            
            await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        
        except Exception as e:
            logger.error(f"Error in help_command: {e}")
            await update.message.reply_text("❌ An error occurred while showing help.")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular messages (potential word submissions)."""
        try:
            if not update.effective_chat or not update.effective_user or not update.message:
                return
            
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            message_text = update.message.text
            
            if not message_text:
                return
            
            # Check if there's an active game
            game_state = self.game_manager.get_game_status(chat_id)
            if not game_state or not game_state.is_active:
                return  # Ignore messages when no game is active
            
            # Get the submitting player BEFORE processing the word
            submitting_player = None
            for player in game_state.players:
                if player.user_id == user_id:
                    submitting_player = player
                    break
            
            # Process the word
            result, error_message = await self.game_manager.process_word(chat_id, user_id, message_text)
            
            # Format and send feedback
            feedback = self.game_manager.format_word_feedback(result, error_message, message_text)
            
            if result == GameResult.VALID_WORD:
                # Cancel current timer
                await self.timer_manager.cancel_turn_timer(chat_id)
                
                # Get updated game state
                updated_state = self.game_manager.get_game_status(chat_id)
                
                # ALWAYS send announcement for valid words
                if updated_state and submitting_player:
                    try:
                        # 1. 发送"提交成功"公告
                        hints = self.game_manager.get_word_hints(chat_id)
                        announcement = self.announcer.formatter.format_valid_word_announcement(
                            message_text, submitting_player, updated_state, hints
                        )
                        
                        await self._send_message_direct(
                            chat_id,
                            announcement,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        
                        # 2. 发送"下一轮挑战"提示
                        if updated_state.is_active:
                            try:
                                next_announcement = self.announcer.formatter.format_next_turn_announcement(updated_state)
                                await self._send_message_direct(
                                    chat_id,
                                    next_announcement,
                                    parse_mode=ParseMode.MARKDOWN
                                )
                            except Exception as e:
                                logger.error(f"Error sending next turn announcement: {e}")
                                # 备用简单提示
                                current_player = updated_state.get_current_player()
                                if current_player:
                                    simple_next = f"🎯 Next Challenge:\n👤 Turn: {current_player.display_name}\n🔤 Letter: **{updated_state.current_letter}**\n📏 Length: {updated_state.required_length} letters"
                                    await self._send_message_direct(chat_id, simple_next, parse_mode=ParseMode.MARKDOWN)
                        
                    except Exception as e:
                        logger.error(f"Error sending valid word announcement: {e}")
                        # Fallback to basic feedback
                        await update.message.reply_text(f"✅ {submitting_player.display_name} submitted '{message_text}'")
                        
                        # 3. 启动下一回合计时器
                        if updated_state.is_active:
                            await self.timer_manager.start_turn_timer(chat_id)
                    else:
                        # Fallback if no updated state or submitting player
                        await update.message.reply_text(feedback)
            
            elif result in [GameResult.INVALID_LETTER, GameResult.INVALID_LENGTH, 
                          GameResult.INVALID_WORD, GameResult.VALIDATION_ERROR]:
                # Send error feedback but don't advance turn
                await update.message.reply_text(feedback)
            
            # Ignore WRONG_PLAYER silently or send a brief message
            elif result == GameResult.WRONG_PLAYER:
                # Send feedback to let the user know it's not their turn
                if feedback:
                    await update.message.reply_text(feedback)
        
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
            # Don't send error messages for regular message handling to avoid spam
    
    async def _send_announcement(self, chat_id: int, event_type: str, **kwargs) -> None:
        """Send game announcements (used by timer manager)."""
        try:
            if not self.application:
                return
            
            if event_type == "player_eliminated":
                eliminated_player = kwargs.get('eliminated_player')
                reason = kwargs.get('reason', 'timeout')
                
                if eliminated_player:
                    await self.announcer.announce_player_eliminated(chat_id, eliminated_player, reason)
            
            elif event_type == "game_ended":
                winner = kwargs.get('winner')
                await self.announcer.announce_winner(chat_id, winner)
            
            elif event_type == "next_turn":
                game_state = kwargs.get('game_state')
                current_player = kwargs.get('current_player')
                
                if game_state and current_player:
                    message = (
                        f"🎯 **Next Turn:**\n"
                        f"📍 Player: {current_player}\n"
                        f"🔤 Letter: **{game_state.current_letter}**\n"
                        f"📏 Min Length: **{game_state.required_length}** letters\n\n"
                        f"💡 Need a word starting with '{game_state.current_letter}' "
                        f"(at least {game_state.required_length} letters long)"
                    )
                    
                    await self.application.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN
                    )
            
            elif event_type == "warning":
                current_player = kwargs.get('current_player')
                remaining_seconds = kwargs.get('remaining_seconds')
                
                if current_player and remaining_seconds:
                    message = f"⚠️ {current_player}, you have **{remaining_seconds}** seconds left!"
                    
                    await self.application.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN
                    )
        
        except Exception as e:
            logger.error(f"Error sending announcement to chat {chat_id}: {e}")
    
    async def _send_message_direct(self, chat_id: int, text: str, parse_mode: Optional[str] = None) -> None:
        """Send message directly through the bot application."""
        async def send_operation():
            if self.application and self.application.bot:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
        
        try:
            await error_handler.retry_with_backoff(
                send_operation,
                "send_message",
                context={'chat_id': chat_id, 'text_length': len(text)}
            )
        except Exception as e:
            logger.error(f"Failed to send message to chat {chat_id} after retries: {e}")
    
    async def shutdown(self) -> None:
        """Clean shutdown of the bot."""
        try:
            if self.timer_manager:
                await self.timer_manager.cleanup()
            logger.info("Telegram bot shut down cleanly")
        except Exception as e:
            logger.error(f"Error during bot shutdown: {e}")


def create_telegram_bot(game_manager: GameManager) -> TelegramBot:
    """Factory function to create a TelegramBot instance."""
    return TelegramBot(game_manager)