def format_guesses(guesses: list[dict]) -> str:
    """Format unique guesses in the same order for both answer interfaces."""
    unique_guesses = sorted({(g.get("guess_text") or "").lower() for g in guesses})
    return (
        "\n".join(f"{i + 1}. {guess}" for i, guess in enumerate(unique_guesses))
        if unique_guesses
        else "No guesses yet."
    )


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
