import discord
import logging
from discord.ext import commands
from src.cfg.main import ConfigReader
from src.core.guess_handler import AlreadyAnsweredCorrectlyError, JinxedError
from src.core.powerup import PowerUpError


class AnswerModal(discord.ui.Modal):
    """Modal for players to submit their answer to the daily trivia question.

    The question text is shown in the channel message; players click the Answer button
    and type their answer here when ready. Previous guesses for this question are
    displayed as a read-only field for reference.
    """

    def __init__(self, bot, question_text: str, player_id: int):
        super().__init__(title="Submit Your Answer", timeout=300)
        self.bot = bot
        self.question_text = question_text
        self.player_id = player_id

        # Fetch and format previous guesses for this player on this question
        daily_question_id = bot.game.daily_question_id
        if daily_question_id:
            guesses = bot.game.data_manager.read_guess_history(user_id=player_id)
            all_guesses = [
                g.get("guess_text")
                for g in guesses
                if g.get("daily_question_id") == daily_question_id
            ]
            # Deduplicate and sort guesses
            unique_guesses = sorted({(g or "").lower() for g in all_guesses})
            guesses_placeholder = (
                "Your previous guesses:\n"
                + "\n".join(f"{i+1}. {g}" for i, g in enumerate(unique_guesses))
                if unique_guesses
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

            # Determine if answer has been revealed
            is_revealed = False
            try:
                morning_task = self.bot.morning_message_task
                evening_task = self.bot.evening_message_task
                if morning_task.is_running() and evening_task.is_running():
                    if morning_task.next_iteration < evening_task.next_iteration:
                        is_revealed = True
            except Exception:
                pass

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

            # Sync the newly-calculated daily_state back to PowerUpManager
            daily_state_new = result.get("daily_state_new", {})
            powerup_manager = self.bot.game.managers.get("powerup")
            if powerup_manager and daily_state_new:
                for user_id, player_state in daily_state_new.items():
                    powerup_manager.daily_state[user_id] = player_state

            # Public message
            public_msg = f"**Score Adjustment:**\n{header}{summary}"
            if result.get("details"):
                public_msg += "\n\n**Details:**\n"
                for d in result["details"]:
                    badges = "".join(d["badges"])
                    sb = d["season_score_before"] if use_season else d["score_before"]
                    sa = d["season_score_after"] if use_season else d["score_after"]
                    public_msg += (
                        f"<@{d['user_id']}>: {sb} -> {sa} ({d['diff']:+}) {badges}\n"
                    )
            if result.get("rest_cleared_players"):
                mentions = " ".join(
                    f"<@{r['user_id']}>" for r in result["rest_cleared_players"]
                )
                public_msg += (
                    f"\nRest revoked — got it right with the new answer: {mentions}"
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

            # Build the preview message
            use_season = self.bot.game.season_manager.enabled

            preview_msg = f"**[DRY RUN PREVIEW]**\nAnswer: `{answer_text}`\n\n"
            preview_msg += f"Would update {result['updated_players']} players.\n"
            preview_msg += f"Total points to refund: {result['total_refunded']}."

            if result.get("age_warning"):
                preview_msg = result["age_warning"] + "\n\n" + preview_msg

            if result.get("details"):
                preview_msg += "\n\n**Changes:**\n"
                for d in result["details"]:
                    badges = "".join(d["badges"])
                    sb = d["season_score_before"] if use_season else d["score_before"]
                    sa = d["season_score_after"] if use_season else d["score_after"]
                    preview_msg += (
                        f"{d['name']}: {sb} → {sa} ({d['diff']:+}) {badges}\n"
                    )

            if result.get("rest_cleared_players"):
                names = ", ".join(r["name"] for r in result["rest_cleared_players"])
                preview_msg += f"\n**Rest revoked (newly correct):** {names}"

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
            player = player_manager.get_or_create_player(
                str(self.member.id), self.member.display_name
            )

            player_manager.update_score(str(self.member.id), amount)

            if streak is not None:
                player_manager.set_streak(str(self.member.id), streak)

            player = player_manager.get_player(str(self.member.id))
            if not player:
                await interaction.followup.send(
                    f"❌ Could not find player {self.member.display_name} after refund.",
                    ephemeral=True,
                )
                return

            # Log the adjustment
            self.bot.data_manager.log_score_adjustment(
                player_id=str(self.member.id),
                admin_id=str(interaction.user.id),
                amount=amount,
                reason=reason,
            )

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
