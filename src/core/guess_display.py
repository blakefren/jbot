from dataclasses import dataclass


@dataclass(frozen=True)
class GuessOutcome:
    """Discord-neutral result of submitting one guess."""

    private_message: str
    public_message: str | None = None


def process_guess(
    game, player_id: int, player_name: str, guess: str, mention: str
) -> GuessOutcome:
    """Submit a guess and build the shared private/public confirmation outcome."""
    from src.cfg.main import ConfigReader
    from src.core.guess_handler import AlreadyAnsweredCorrectlyError, JinxedError

    if not game.daily_q:
        return GuessOutcome("There is no active question.")

    try:
        is_correct, num_guesses, points_earned, bonus_messages = game.handle_guess(
            player_id, player_name, guess
        )
    except AlreadyAnsweredCorrectlyError:
        return GuessOutcome("You already solved today.")
    except JinxedError as exc:
        emoji_silenced = ConfigReader().get("JBOT_EMOJI_SILENCED", "🤐")
        return GuessOutcome(f"{emoji_silenced} {exc.message}")
    except Exception:
        return GuessOutcome(
            "An error occurred while processing your answer. Please try again later.",
        )

    daily_question_id = game.daily_question_id
    guesses = (
        game.data_manager.read_guess_history(
            user_id=player_id, daily_question_id=daily_question_id
        )
        if daily_question_id
        else []
    )
    guesses_text = format_guesses(guesses)

    if is_correct:
        bonus_str = ""
        if bonus_messages:
            bonus_str = "\n" + "\n".join(bonus_messages)
        private_message = truncate_discord_text(
            f"Correct! Nicely done.\n"
            f"**Answer:** {game.daily_q.answer}\n\n"
            f"Guesses:\n{guesses_text}",
            2000,
        )
        public_message = (
            f"{mention} solved it in {num_guesses}! "
            f"(+**{points_earned}** pts){bonus_str}"
        )
        return GuessOutcome(private_message, public_message)

    private_message = truncate_discord_text(
        f"Sorry, that was incorrect.\n\nGuesses:\n{guesses_text}", 2000
    )
    return GuessOutcome(private_message)


def format_guesses(guesses: list[dict]) -> str:
    """Format unique guesses in the same order for both answer interfaces."""
    unique_guesses = sorted({(g.get("guess_text") or "").lower() for g in guesses})
    return (
        "\n".join(f"{i + 1}. {guess}" for i, guess in enumerate(unique_guesses))
        if unique_guesses
        else "No guesses yet."
    )


def is_answer_revealed(bot) -> bool:
    """Return whether scheduled morning/evening tasks indicate the answer was revealed."""
    try:
        morning_task = bot.morning_message_task
        evening_task = bot.evening_message_task
        if morning_task.is_running() and evening_task.is_running():
            return morning_task.next_iteration < evening_task.next_iteration
    except Exception:
        pass
    return False


def format_answer_correction_preview(
    result: dict, answer_text: str, is_revealed: bool = False
) -> str:
    """Build the shared dry-run preview for an answer correction."""
    header = (
        f"Added ||{answer_text}|| as a correct answer.\n"
        if is_revealed
        else "Added alternative answer.\n"
    )
    preview = (
        "**[DRY RUN]** No changes applied. "
        "Run with `apply=True` to execute.\n"
        f"{header}\n"
    )
    preview += (
        f"Would update {result['updated_players']} players.\n"
        f"Total points to refund: {result['total_refunded']}."
    )
    if result.get("age_warning"):
        preview = result["age_warning"] + "\n\n" + preview

    if result.get("details"):
        preview += "\n\n**Changes:**\n"
        for detail in result["details"]:
            preview += (
                f"{detail['name']}: {detail['score_before']} -> "
                f"{detail['score_after']} ({detail['diff']:+})"
            )
            badges = "".join(detail.get("badges", []))
            if badges:
                preview += f" {badges}"
            preview += "\n"

    if result.get("rest_cleared_players"):
        names = ", ".join(row["name"] for row in result["rest_cleared_players"])
        preview += f"\n**Rest revoked (newly correct):** {names}"
    return preview


def format_answer_correction_applied(
    result: dict,
    answer_text: str,
    is_revealed: bool,
    use_season: bool,
) -> str:
    """Build the shared public applied-correction message."""
    header = (
        f"Added ||{answer_text}|| as a correct answer.\n"
        if is_revealed
        else f"Added alternative answer.\n"
    )
    summary = (
        f"Updated scores for {result['updated_players']} players.\n"
        f"Total points refunded: {result['total_refunded']}."
    )
    if result.get("age_warning"):
        summary = result["age_warning"] + "\n" + summary

    message = f"**Score Adjustment:**\n{header}{summary}"
    if result.get("details"):
        message += "\n\n**Details:**\n"
        for detail in result["details"]:
            if use_season:
                before = detail["season_score_before"]
                after = detail["season_score_after"]
            else:
                before = detail["score_before"]
                after = detail["score_after"]
            badges = "".join(detail.get("badges", []))
            message += (
                f"<@{detail['user_id']}>: {before} -> {after} "
                f"({detail['diff']:+}) {badges}\n"
            )

    if result.get("rest_cleared_players"):
        mentions = " ".join(
            f"<@{row['user_id']}>" for row in result["rest_cleared_players"]
        )
        message += f"\nRest revoked — got it right with the new answer: {mentions}"
    return message


def truncate_discord_text(text: str, limit: int) -> str:
    """Keep text within Discord's limit, indicating when content is omitted."""

    def length(value: str) -> int:
        return sum(2 if ord(char) > 0xFFFF else 1 for char in value)

    if length(text) <= limit:
        return text

    suffix = "\n... (truncated)"
    remaining = limit - length(suffix)
    result = []
    for char in text:
        size = 2 if ord(char) > 0xFFFF else 1
        if size > remaining:
            break
        result.append(char)
        remaining -= size
    return "".join(result) + suffix
