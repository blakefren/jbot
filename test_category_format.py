"""
Quick script to demonstrate the new Jeopardy! category formatting.
Run this to see examples of how categories will appear in the bot.
"""

from data.readers.tsv import read_jeopardy_questions
import random

# This would work with the actual dataset file
# For demonstration, here's what categories would look like:

examples = {
    "easy": [
        "Jeopardy! (easy) | THE MOOSE OUT FRONT",
        "Jeopardy! (easy) | WORLD HISTORY",
        "Jeopardy! (easy) | LITERARY CHARACTERS",
        "Jeopardy! (easy) | SCIENCE",
    ],
    "medium": [
        "Jeopardy! (medium) | POTENT POTABLES",
        "Jeopardy! (medium) | ANCIENT CIVILIZATIONS",
        "Jeopardy! (medium) | SPORTS",
        "Jeopardy! (medium) | GEOGRAPHY",
    ],
    "hard": [
        "Jeopardy! (hard) | WORD ORIGINS",
        "Jeopardy! (hard) | FAMOUS BATTLES",
        "Jeopardy! (hard) | U.S. PRESIDENTS",
        "Jeopardy! (hard) | FINAL JEOPARDY CATEGORY",
    ],
}

print("=" * 70)
print("JEOPARDY! CATEGORY FORMAT EXAMPLES")
print("=" * 70)

for difficulty, categories in examples.items():
    print(f"\n{difficulty.upper()} Difficulty:")
    print("-" * 70)
    for cat in categories:
        print(f"  {cat}")

print("\n" + "=" * 70)
print("These categories will now appear in Discord when questions are sent!")
print("=" * 70)
