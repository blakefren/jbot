import discord
import logging
from discord.ext import commands
from src.cfg.main import ConfigReader
from src.core.guess_handler import AlreadyAnsweredCorrectlyError, JinxedError


class AnswerModal(discord.ui.Modal):
    """Modal for players to submit their answer to the daily trivia question."""

    def __init__(self, bot, question_text: str):
        super().__init__(title="Submit Your Answer", timeout=300)
        self.bot = bot
        self.question_text = question_text

        # Add a text input field for the answer
        self.answer_input = discord.ui.TextInput(
            label="Your Answer",
            placeholder="Type your answer here...",
            required=True,
            max_length=500,
        )
        self.add_item(self.answer_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Called when the user submits the modal."""
        await interaction.response.defer(ephemeral=True)

        guess = str(self.answer_input.value).strip()

        if not self.bot.game.daily_q:
            await interaction.followup.send(
                "There is no active question.", ephemeral=True
            )
            return

        try:
            player_id = interaction.user.id
            player_name = interaction.user.display_name
            (
                is_correct,
                num_guesses,
                points_earned,
                bonus_messages,
            ) = self.bot.game.handle_guess(player_id, player_name, guess)
        except AlreadyAnsweredCorrectlyError:
            await interaction.followup.send("You already solved today.", ephemeral=True)
            return
        except JinxedError as e:
            emoji_silenced = ConfigReader().get("JBOT_EMOJI_SILENCED", "🤐")
            await interaction.followup.send(
                f"{emoji_silenced} {e.message}", ephemeral=True
            )
            return
        except Exception as e:
            logging.error(f"Error handling guess from modal: {e}")
            await interaction.followup.send(
                "An error occurred while processing your answer. Please try again later.",
                ephemeral=True,
            )
            return

        # TODO: a lot of this logic is duplicated from trivia.py and could be
        # refactored into a shared utility function.

        # Retrieve all guesses for this player for the current question
        daily_question_id = self.bot.game.daily_question_id
        if not daily_question_id:
            all_guesses = []
        else:
            guesses = self.bot.game.data_manager.read_guess_history(user_id=player_id)
            all_guesses = [
                g.get("guess_text")
                for g in guesses
                if g.get("daily_question_id") == daily_question_id
            ]

        # Deduplicate and sort guesses
        unique_guesses = sorted({(g or "").lower() for g in all_guesses})
        guesses_text = (
            "\n".join(f"{i+1}. {g}" for i, g in enumerate(unique_guesses))
            if unique_guesses
            else "No guesses yet."
        )

        # Send confirmation message
        if is_correct:
            # Construct bonus string
            bonus_str = ""
            if bonus_messages:
                bonus_str = "\n" + "\n".join(f"{msg}" for msg in bonus_messages)

            # Send the private confirmation
            await interaction.followup.send(
                f"Correct! Nicely done.\n"
                f"**Answer:** {self.bot.game.daily_q.answer}\n\n"
                f"Guesses:\n{guesses_text}",
                ephemeral=True,
            )
            # Announce the correct answer publicly in the channel
            channel = interaction.channel
            if channel:
                await channel.send(
                    f"{interaction.user.mention} solved it in {num_guesses}! (+**{points_earned}** pts){bonus_str}"
                )
        else:
            # Send the private confirmation for an incorrect answer
            await interaction.followup.send(
                f"Sorry, that was incorrect.\n\nGuesses:\n{guesses_text}",
                ephemeral=True,
            )


class AnswerView(discord.ui.View):
    """View containing the button to open the answer modal."""

    def __init__(self, bot):
        super().__init__(timeout=None)  # No timeout for persistence
        self.bot = bot

    @discord.ui.button(
        label="Answer",
        style=discord.ButtonStyle.primary,
        custom_id="trivia:answer",
    )
    async def answer_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Button callback that opens the answer modal."""
        if not self.bot.game.daily_q:
            await interaction.response.send_message(
                "There is no active question.", ephemeral=True
            )
            return

        # Create and show the modal
        modal = AnswerModal(self.bot, self.bot.game.daily_q.question)
        await interaction.response.send_modal(modal)
