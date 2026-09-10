import discord
import logging
from discord.ext import commands
from src.cfg.main import ConfigReader
from src.core.guess_handler import AlreadyAnsweredCorrectlyError, JinxedError
from src.core.powerup import PowerUpError


class AnswerModal(discord.ui.Modal):
    """Modal for players to submit their answer to the daily trivia question.

    The question text is shown in the channel message; players click the Answer button
    and type their answer here when ready.
    """

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


class JinxSelectView(discord.ui.View):
    """Sub-view with UserSelect to choose a player to jinx."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choose a player to jinx...",
        min_values=1,
        max_values=1,
        custom_id="jinx_user_select",
    )
    async def select_jinx_target(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        """Handle player selection for jinx."""
        await interaction.response.defer(ephemeral=True)

        if not select.values:
            await interaction.followup.send("No player selected.", ephemeral=True)
            return

        target_id = str(select.values[0].id)

        try:
            manager = self.bot.game.managers.get("powerup")
            if not manager:
                await interaction.followup.send(
                    "Power-ups are not available.", ephemeral=True
                )
                return

            target_state = manager.daily_state.get(target_id)
            target_already_answered = (
                target_state is not None and target_state.is_correct
            )
            result = manager.jinx(
                str(interaction.user.id), target_id, self.bot.game.daily_question_id
            )
            await interaction.followup.send(
                result, ephemeral=not target_already_answered
            )
        except PowerUpError as e:
            await interaction.followup.send(str(e), ephemeral=True)
        except Exception as e:
            logging.error(f"Error processing jinx: {e}")
            await interaction.followup.send(
                "An error occurred. Please try again later.", ephemeral=True
            )


class StealSelectView(discord.ui.View):
    """Sub-view with UserSelect to choose a player to steal from."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choose a player to steal from...",
        min_values=1,
        max_values=1,
        custom_id="steal_user_select",
    )
    async def select_steal_target(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        """Handle player selection for steal."""
        await interaction.response.defer(ephemeral=True)

        if not select.values:
            await interaction.followup.send("No player selected.", ephemeral=True)
            return

        target_id = str(select.values[0].id)

        try:
            manager = self.bot.game.managers.get("powerup")
            if not manager:
                await interaction.followup.send(
                    "Power-ups are not available.", ephemeral=True
                )
                return

            target_state = manager.daily_state.get(target_id)
            target_already_answered = (
                target_state is not None and target_state.is_correct
            )
            result = manager.steal(
                str(interaction.user.id), target_id, self.bot.game.daily_question_id
            )
            await interaction.followup.send(
                result, ephemeral=not target_already_answered
            )
        except PowerUpError as e:
            await interaction.followup.send(str(e), ephemeral=True)
        except Exception as e:
            logging.error(f"Error processing steal: {e}")
            await interaction.followup.send(
                "An error occurred. Please try again later.", ephemeral=True
            )


class RestConfirmationView(discord.ui.View):
    """Sub-view with confirmation button for rest command."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.danger,
        custom_id="rest_confirm",
    )
    async def confirm_rest(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Confirm and execute rest command."""
        await interaction.response.defer(ephemeral=True)

        if not self.bot.game.daily_q:
            await interaction.followup.send(
                "There is no active question right now.", ephemeral=True
            )
            return

        try:
            manager = self.bot.game.managers.get("powerup")
            if not manager:
                await interaction.followup.send(
                    "Power-ups are not available.", ephemeral=True
                )
                return

            public_msg, private_msg = manager.rest(
                str(interaction.user.id),
                self.bot.game.daily_question_id,
                self.bot.game.daily_q.answer,
            )
            # Send public announcement
            channel = interaction.channel
            if channel:
                await channel.send(public_msg)
            # Send private confirmation
            await interaction.followup.send(private_msg, ephemeral=True)
        except Exception as e:
            logging.error(f"Error processing rest: {e}")
            await interaction.followup.send(str(e), ephemeral=True)


class GameActionView(discord.ui.View):
    """Main view with buttons for Answer, Jinx, Steal, and Rest.

    This is the only view that needs to be registered with the bot.
    Sub-views are shown via the button callbacks.
    """

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
        """Button callback that opens the answer modal with the question."""
        if not self.bot.game.daily_q:
            await interaction.response.send_message(
                "There is no active question.", ephemeral=True
            )
            return

        # Show the modal with the question displayed
        modal = AnswerModal(self.bot, self.bot.game.daily_q.question)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Jinx",
        style=discord.ButtonStyle.secondary,
        custom_id="trivia:jinx",
    )
    async def jinx_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Button callback that shows the jinx target selection."""
        if not self.bot.game.daily_q:
            await interaction.response.send_message(
                "There is no active question.", ephemeral=True
            )
            return

        jinx_description = (
            "**JINX** — Silence yourself until the hint, then get a share of the target's score when they answer. "
            "Each wrong guess they make costs you.\n\n"
            "Select a player to jinx:"
        )
        view = JinxSelectView(self.bot)
        await interaction.response.send_message(
            jinx_description, view=view, ephemeral=True
        )

    @discord.ui.button(
        label="Steal",
        style=discord.ButtonStyle.secondary,
        custom_id="trivia:steal",
    )
    async def steal_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Button callback that shows the steal target selection."""
        if not self.bot.game.daily_q:
            await interaction.response.send_message(
                "There is no active question.", ephemeral=True
            )
            return

        steal_description = (
            "**STEAL** — Pay streak days upfront to receive all non-streak bonuses "
            "(try, before-hint, fastest-answer) earned by the target when they answer.\n\n"
            "Select a player to steal from:"
        )
        view = StealSelectView(self.bot)
        await interaction.response.send_message(
            steal_description, view=view, ephemeral=True
        )

    @discord.ui.button(
        label="Rest",
        style=discord.ButtonStyle.danger,
        custom_id="trivia:rest",
    )
    async def rest_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Button callback that shows the rest confirmation."""
        if not self.bot.game.daily_q:
            await interaction.response.send_message(
                "There is no active question right now.", ephemeral=True
            )
            return

        rest_description = (
            "**REST** — Skip today's question, keep your streak, and stack a bonus for your next answer. "
            "Incoming jinx/steal will be blocked.\n\n"
            "⚠️ Confirm to rest today?"
        )
        view = RestConfirmationView(self.bot)
        await interaction.response.send_message(
            rest_description, view=view, ephemeral=True
        )


async def setup(bot):
    """Setup function required by cog loader.

    Modal and View components are not cogs but rather Discord UI components
    that are instantiated and managed by the discord.py main bot file.
    This function exists to satisfy the cog loader's requirements.
    """
    pass
