import discord
import logging
from discord.ext import commands
from src.cfg.main import ConfigReader
from src.core.guess_display import (
    format_answer_correction_applied,
    format_answer_correction_preview,
    is_answer_revealed,
    format_guesses,
    process_guess,
    truncate_discord_text,
)
from src.core.guess_handler import AlreadyAnsweredCorrectlyError, JinxedError
from src.core.powerup import PowerUpError


class AnswerModal(discord.ui.Modal):
    """Modal for players to submit their answer to the daily trivia question.

    The question text is shown in the channel message; players click the Answer button
    and type their answer here when ready. Previous guesses for this question are
    displayed in the input placeholder for reference.
    """

    def __init__(self, bot, question_text: str, player_id: int):
        super().__init__(title="Submit Your Answer", timeout=300)
        self.bot = bot
        self.question_text = question_text
        self.player_id = player_id

        # Fetch and format previous guesses for this player on this question
        daily_question_id = bot.game.daily_question_id
        if daily_question_id:
            guesses = bot.game.data_manager.read_guess_history(
                user_id=player_id, daily_question_id=daily_question_id
            )
            guesses_placeholder = (
                truncate_discord_text(
                    "Your previous guesses:\n" + format_guesses(guesses), 100
                )
                if guesses
                else "Type your answer here..."
            )
        else:
            guesses_placeholder = "Type your answer here..."

        # Add a text input field for the answer
        self.answer_input = discord.ui.TextInput(
            label="Your Answer",
            placeholder=guesses_placeholder,
            required=True,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.answer_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Called when the user submits the modal."""
        await interaction.response.defer(ephemeral=True)

        guess = str(self.answer_input.value).strip()

        outcome = process_guess(
            self.bot.game,
            interaction.user.id,
            interaction.user.display_name,
            guess,
            interaction.user.mention,
        )
        await interaction.followup.send(outcome.private_message, ephemeral=True)
        if outcome.public_message and interaction.channel:
            await interaction.channel.send(outcome.public_message)


async def _send_power_result(interaction: discord.Interaction, result: str):
    """Deliver a power-up result without replying to the (ephemeral) menu message."""
    public = getattr(result, "public", False)
    if public and interaction.channel:
        await interaction.channel.send(result)
        await interaction.edit_original_response(content="✅ Done.", view=None)
    else:
        await interaction.edit_original_response(content=result, view=None)


class JinxSelectView(discord.ui.View):
    """Sub-view with StringSelect to choose an eligible player to jinx.

    Options are filtered to only show players who:
    - Haven't been jinxed yet
    - Are not resting
    - The attacker hasn't been attacked by (retaliation block)
    """

    def __init__(self, bot, attacker_id: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.attacker_id = attacker_id

        # Get valid targets and build options
        manager = self.bot.game.managers.get("powerup")
        valid_targets = (
            manager.get_valid_jinx_targets(attacker_id, self.bot.game.daily_question_id)
            if manager
            else []
        )

        # Build select options from valid targets
        options = [
            discord.SelectOption(label=name, value=player_id)
            for player_id, name in valid_targets
        ]

        # Create the select if there are valid targets
        if options:
            self.select.options = options
        else:
            # Disable the view if no valid targets
            self.select.disabled = True

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Choose a player to jinx...",
        min_values=1,
        max_values=1,
        custom_id="jinx_string_select",
    )
    async def select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle player selection for jinx."""
        await interaction.response.defer(ephemeral=True)

        if not select.values:
            await interaction.followup.send("No player selected.", ephemeral=True)
            return

        target_id = select.values[0]

        try:
            manager = self.bot.game.managers.get("powerup")
            if not manager:
                await interaction.followup.send(
                    "Power-ups are not available.", ephemeral=True
                )
                return

            result = manager.jinx(
                str(interaction.user.id), target_id, self.bot.game.daily_question_id
            )
            await _send_power_result(interaction, result)
        except PowerUpError as e:
            await interaction.followup.send(str(e), ephemeral=True)
        except Exception as e:
            logging.error(f"Error processing jinx: {e}")
            await interaction.followup.send(
                "An error occurred. Please try again later.", ephemeral=True
            )


class StealSelectView(discord.ui.View):
    """Sub-view with StringSelect to choose an eligible player to steal from.

    Options are filtered to only show players who:
    - Are not already targeted for steal
    - Are not resting
    - The thief hasn't been attacked by (retaliation block)
    """

    def __init__(self, bot, thief_id: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.thief_id = thief_id

        # Get valid targets and build options
        manager = self.bot.game.managers.get("powerup")
        valid_targets = (
            manager.get_valid_steal_targets(thief_id, self.bot.game.daily_question_id)
            if manager
            else []
        )

        # Build select options from valid targets
        options = [
            discord.SelectOption(label=name, value=player_id)
            for player_id, name in valid_targets
        ]

        # Create the select if there are valid targets
        if options:
            self.select.options = options
        else:
            # Disable the view if no valid targets
            self.select.disabled = True

    @discord.ui.select(
        cls=discord.ui.Select,
        placeholder="Choose a player to steal from...",
        min_values=1,
        max_values=1,
        custom_id="steal_string_select",
    )
    async def select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle player selection for steal."""
        await interaction.response.defer(ephemeral=True)

        if not select.values:
            await interaction.followup.send("No player selected.", ephemeral=True)
            return

        target_id = select.values[0]

        try:
            manager = self.bot.game.managers.get("powerup")
            if not manager:
                await interaction.followup.send(
                    "Power-ups are not available.", ephemeral=True
                )
                return

            result = manager.steal(
                str(interaction.user.id), target_id, self.bot.game.daily_question_id
            )
            await _send_power_result(interaction, result)
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


class SkipConfirmationView(discord.ui.View):
    """Sub-view with confirmation button for skip command."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Confirm Skip",
        style=discord.ButtonStyle.danger,
        custom_id="admin:skip_confirm",
    )
    async def confirm_skip(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Confirm and execute skip command."""
        await interaction.response.defer(ephemeral=True)

        if not self.bot.game.daily_q:
            await interaction.followup.send(
                "There is no active question to skip.", ephemeral=True
            )
            return

        try:
            if self.bot.game.reset_daily_question():
                new_question = self.bot.game.daily_q
                question_content = self.bot.game.format_question(new_question)
                await interaction.channel.send(
                    f"The daily question has been skipped. The new question is:\n{question_content}"
                )
                await interaction.followup.send("✅ Question skipped.", ephemeral=True)
            else:
                await interaction.followup.send(
                    "❌ Failed to skip the daily question. Check the logs.",
                    ephemeral=True,
                )
        except Exception as e:
            logging.error(f"Error skipping question: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class AddAnswerConfirmationView(discord.ui.View):
    """View with Apply/Cancel buttons after dry-run preview."""

    def __init__(self, bot, answer_text: str, admin_id: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.answer_text = answer_text
        self.admin_id = admin_id

    @discord.ui.button(
        label="Apply",
        style=discord.ButtonStyle.success,
        custom_id="admin:add_answer_apply",
    )
    async def apply_answer(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Apply the answer change."""
        await interaction.response.defer(ephemeral=True)

        try:
            result = self.bot.game.recalculate_scores_for_new_answer(
                self.answer_text, self.admin_id, dry_run=False
            )

            if result["status"] == "error":
                await interaction.followup.send(
                    f"❌ Error: {result['message']}", ephemeral=True
                )
                return

            is_revealed = is_answer_revealed(self.bot)

            # Build the message body
            if is_revealed:
                header = f"Added ||{self.answer_text}|| as a correct answer.\n"
            else:
                header = "Added alternative answer.\n"

            summary = (
                f"Updated scores for {result['updated_players']} players.\n"
                f"Total points refunded: {result['total_refunded']}."
            )
            if result.get("age_warning"):
                summary = result["age_warning"] + "\n" + summary

            use_season = self.bot.game.season_manager.enabled

            public_msg = format_answer_correction_applied(
                result,
                self.answer_text,
                is_revealed,
                use_season,
            )

            await interaction.channel.send(public_msg)
            await interaction.followup.send(
                "✅ Answer applied and scores updated.", ephemeral=True
            )

        except Exception as e:
            logging.error(f"Error applying answer: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="admin:add_answer_cancel",
    )
    async def cancel_answer(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Cancel the answer change."""
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Cancelled.", ephemeral=True)


class AddAnswerModal(discord.ui.Modal):
    """Modal for admins to add an alternative answer."""

    def __init__(self, bot):
        super().__init__(title="Add Alternative Answer", timeout=300)
        self.bot = bot

        self.answer_input = discord.ui.TextInput(
            label="Answer Text",
            placeholder="Enter the alternative answer...",
            required=True,
            max_length=500,
        )
        self.add_item(self.answer_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Called when the admin submits the modal."""
        await interaction.response.defer(ephemeral=True)

        answer_text = str(self.answer_input.value).strip()

        try:
            # Do a dry-run first
            result = self.bot.game.recalculate_scores_for_new_answer(
                answer_text, str(interaction.user.id), dry_run=True
            )

            if result["status"] == "error":
                await interaction.followup.send(
                    f"❌ Error: {result['message']}", ephemeral=True
                )
                return

            preview_msg = format_answer_correction_preview(
                result,
                answer_text,
                is_revealed=is_answer_revealed(self.bot),
            )

            # Show preview with Apply/Cancel buttons
            view = AddAnswerConfirmationView(
                self.bot, answer_text, str(interaction.user.id)
            )
            await interaction.followup.send(preview_msg, view=view, ephemeral=True)

        except Exception as e:
            logging.error(f"Error preparing answer preview: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class RefundSelectView(discord.ui.View):
    """Sub-view with UserSelect to choose a player to refund."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choose a player to refund...",
        min_values=1,
        max_values=1,
        custom_id="admin:refund_user_select",
    )
    async def select_refund_target(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        """Handle player selection for refund."""
        await interaction.response.defer(ephemeral=True)

        if not select.values:
            await interaction.followup.send("No player selected.", ephemeral=True)
            return

        member = select.values[0]
        modal = RefundModal(self.bot, member)
        await interaction.followup.send_modal(modal)


class RefundModal(discord.ui.Modal):
    """Modal for admins to enter refund details."""

    def __init__(self, bot, member: discord.Member):
        super().__init__(title="Refund Player", timeout=300)
        self.bot = bot
        self.member = member

        self.amount_input = discord.ui.TextInput(
            label="Amount (points)",
            placeholder="e.g., 50",
            required=True,
            max_length=10,
        )
        self.add_item(self.amount_input)

        self.streak_input = discord.ui.TextInput(
            label="Streak (optional, leave blank to skip)",
            placeholder="e.g., 5",
            required=False,
            max_length=10,
        )
        self.add_item(self.streak_input)

        self.reason_input = discord.ui.TextInput(
            label="Reason",
            placeholder="Brief reason for the refund...",
            required=True,
            max_length=500,
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Called when the admin submits the refund modal."""
        await interaction.response.defer(ephemeral=True)

        try:
            amount = int(str(self.amount_input.value).strip())
        except ValueError:
            await interaction.followup.send(
                "❌ Amount must be a valid integer.", ephemeral=True
            )
            return

        streak = None
        if self.streak_input.value and str(self.streak_input.value).strip():
            try:
                streak = int(str(self.streak_input.value).strip())
            except ValueError:
                await interaction.followup.send(
                    "❌ Streak must be a valid integer.", ephemeral=True
                )
                return

        reason = str(self.reason_input.value).strip()

        try:
            player_manager = self.bot.player_manager
            player = player_manager.refund_player(
                str(self.member.id),
                self.member.display_name,
                amount,
                streak,
                str(interaction.user.id),
                reason,
            )
            if not player:
                await interaction.followup.send(
                    f"❌ Could not find player {self.member.display_name} after refund.",
                    ephemeral=True,
                )
                return

            msg = (
                f"✅ Refunded {self.member.mention}: {amount:+} (Score: {player.score}"
            )
            if streak is not None:
                msg += f", Streak: {streak}"
            msg += f"). Reason: {reason}"

            await interaction.channel.send(msg)
            await interaction.followup.send("Refund processed.", ephemeral=True)

        except Exception as e:
            logging.error(f"Error processing refund: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class AdminMenuView(discord.ui.View):
    """Sub-view for admin quick actions."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Refund",
        style=discord.ButtonStyle.blurple,
        custom_id="admin:refund",
    )
    async def admin_refund(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Open refund player selection."""
        view = RefundSelectView(self.bot)
        await interaction.response.send_message(
            "Select a player to refund:", view=view, ephemeral=True
        )

    @discord.ui.button(
        label="Add Answer",
        style=discord.ButtonStyle.blurple,
        custom_id="admin:add_answer",
    )
    async def admin_add_answer(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Open add_answer modal."""
        modal = AddAnswerModal(self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Skip Question",
        style=discord.ButtonStyle.blurple,
        custom_id="admin:skip",
    )
    async def admin_skip(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Open skip confirmation."""
        if not self.bot.game.daily_q:
            await interaction.response.send_message(
                "There is no active question to skip.", ephemeral=True
            )
            return

        skip_description = (
            "⚠️ This will skip the current question and load a new one. "
            "Players will see the new question immediately.\n\n"
            "Confirm to skip?"
        )
        view = SkipConfirmationView(self.bot)
        await interaction.response.send_message(
            skip_description, view=view, ephemeral=True
        )


class GameActionView(discord.ui.View):
    """Main view with buttons for Answer, Jinx, Steal, Rest, and Admin.

    This is the only view that needs to be registered with the bot.
    Sub-views are shown via the button callbacks.
    """

    def __init__(self, bot):
        super().__init__(timeout=None)  # No timeout for persistence
        self.bot = bot

        # Load emoji from config and update button labels
        config = ConfigReader()
        emoji_jinx = config.get("JBOT_EMOJI_JINXED", "🧙")
        emoji_steal = config.get("JBOT_EMOJI_STEALING", "💰")
        emoji_rest = config.get("JBOT_EMOJI_REST", "😴")

        # Update button labels with emoji
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "trivia:jinx":
                    item.label = f"{emoji_jinx} Jinx"
                elif item.custom_id == "trivia:steal":
                    item.label = f"{emoji_steal} Steal"
                elif item.custom_id == "trivia:rest":
                    item.label = f"{emoji_rest} Rest"

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

        # Early check: can the player answer (not jinxed before hint, not resting)?
        manager = self.bot.game.managers.get("powerup")
        if manager:
            # Check if hint has been sent to properly validate jinxed players
            hint_timestamp = self.bot.game.data_manager.get_hint_sent_timestamp(
                self.bot.game.daily_question_id
            )
            hint_sent = hint_timestamp is not None
            can_answer, reason = manager.can_answer(
                str(interaction.user.id), hint_sent=hint_sent
            )
            if not can_answer:
                emoji_silenced = ConfigReader().get("JBOT_EMOJI_SILENCED", "🤐")
                await interaction.response.send_message(
                    f"{emoji_silenced} {reason}", ephemeral=True
                )
                return

        # Show the modal with the question displayed and previous guesses
        modal = AnswerModal(
            self.bot, self.bot.game.daily_q.question, interaction.user.id
        )
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
        attacker_id = str(interaction.user.id)

        # Early check: can the player use an attack power-up today?
        manager = self.bot.game.managers.get("powerup")
        if manager:
            can_use, reason = manager.can_use_attack_powerup(attacker_id)
            if not can_use:
                await interaction.response.send_message(reason, ephemeral=True)
                return

        jinx_description = (
            "**JINX** — Silence yourself until the hint, then get a share of the target's score when they answer. "
            "Each wrong guess they make costs you.\n\n"
            "Can be used for preloading if no question is active.\n\n"
            "Select a player to jinx:"
        )
        view = JinxSelectView(self.bot, attacker_id)
        if view.select.disabled:
            await interaction.response.send_message(
                "No eligible targets to jinx. All available players are either already jinxed, resting, or you've been attacked by them.",
                ephemeral=True,
            )
        else:
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
        thief_id = str(interaction.user.id)

        # Early check: can the player use an attack power-up today?
        manager = self.bot.game.managers.get("powerup")
        if manager:
            can_use, reason = manager.can_use_attack_powerup(thief_id)
            if not can_use:
                await interaction.response.send_message(reason, ephemeral=True)
                return

        steal_description = (
            "**STEAL** — Pay streak days upfront to receive all non-streak bonuses "
            "(try, before-hint, fastest-answer) earned by the target when they answer.\n\n"
            "Can be used for preloading if no question is active.\n\n"
            "Select a player to steal from:"
        )
        view = StealSelectView(self.bot, thief_id)
        if view.select.disabled:
            await interaction.response.send_message(
                "No eligible targets to steal from. All available players are either already targeted, resting, or you've been attacked by them.",
                ephemeral=True,
            )
        else:
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

        # Early check: can the player rest (not already resting, not already answered)?
        manager = self.bot.game.managers.get("powerup")
        if manager:
            can_rest, reason = manager.can_rest(str(interaction.user.id))
            if not can_rest:
                emoji_rest = ConfigReader().get("JBOT_EMOJI_REST", "😴")
                await interaction.response.send_message(
                    f"{emoji_rest} {reason}", ephemeral=True
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

    @discord.ui.button(
        label="⚙️ Admin",
        style=discord.ButtonStyle.secondary,
        custom_id="trivia:admin",
    )
    async def admin_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Button callback that shows the admin menu (admin-only)."""
        # Check if user has administrator permission (same as admin cog)
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You don't have permission to access admin functions.", ephemeral=True
            )
            return

        admin_description = "**Admin Panel** — Select a task:"
        view = AdminMenuView(self.bot)
        await interaction.response.send_message(
            admin_description, view=view, ephemeral=True
        )


async def setup(bot):
    """Setup function required by cog loader.

    Modal and View components are not cogs but rather Discord UI components
    that are instantiated and managed by the discord.py main bot file.
    This function exists to satisfy the cog loader's requirements.
    """
    pass
