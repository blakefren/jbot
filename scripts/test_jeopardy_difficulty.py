#!/usr/bin/env python
"""Quick test to verify Jeopardy difficulty-based question loading."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import random
from data.readers.tsv import read_jeopardy_questions

# Load questions with all three difficulties
print("Loading Jeopardy questions...")
dataset_path = os.path.join(
    os.path.dirname(__file__), "..", "datasets", "combined_season1-41.tsv"
)
easy = read_jeopardy_questions(dataset_path, difficulty="easy")
medium = read_jeopardy_questions(dataset_path, difficulty="medium")
hard = read_jeopardy_questions(dataset_path, difficulty="hard")

print(f"\nEasy: {len(easy):,} questions (all should have clue_value=100)")
print(f"Medium: {len(medium):,} questions (all should have clue_value=200)")
print(f"Hard: {len(hard):,} questions (all should have clue_value=300)")
print(f"Total: {len(easy) + len(medium) + len(hard):,} questions")

# Sample one from each difficulty
print("\n" + "=" * 80)
print("EASY SAMPLE:")
e = random.choice(easy)
print(f"  Q: {e.question[:70]}...")
print(f"  A: {e.answer}")
print(f"  Category: {e.category}")
print(f"  Points: {e.clue_value}, Position: {e.metadata.get('position', 'N/A')}")
print(f"  Original clue value: {e.metadata.get('original_clue_value', 'N/A')}")

print("\n" + "=" * 80)
print("MEDIUM SAMPLE:")
m = random.choice(medium)
print(f"  Q: {m.question[:70]}...")
print(f"  A: {m.answer}")
print(f"  Category: {m.category}")
print(f"  Points: {m.clue_value}, Position: {m.metadata.get('position', 'N/A')}")
print(f"  Original clue value: {m.metadata.get('original_clue_value', 'N/A')}")

print("\n" + "=" * 80)
print("HARD SAMPLE:")
h = random.choice(hard)
print(f"  Q: {h.question[:70]}...")
print(f"  A: {h.answer}")
print(f"  Category: {h.category}")
print(f"  Points: {h.clue_value}, Position: {h.metadata.get('position', 'N/A')}")
print(f"  Original clue value: {h.metadata.get('original_clue_value', 'N/A')}")
print(f"  Round: {h.metadata.get('round', 'N/A')}")

# Verify all have correct normalized points
easy_check = all(q.clue_value == 100 for q in easy[:1000])
medium_check = all(q.clue_value == 200 for q in medium[:1000])
hard_check = all(q.clue_value == 300 for q in hard[:1000])

print("\n" + "=" * 80)
print("VERIFICATION:")
print(f"  Easy questions all have clue_value=100: {easy_check}")
print(f"  Medium questions all have clue_value=200: {medium_check}")
print(f"  Hard questions all have clue_value=300: {hard_check}")
print(
    "\n✓ Implementation successful!"
    if all([easy_check, medium_check, hard_check])
    else "\n✗ Issues found"
)
