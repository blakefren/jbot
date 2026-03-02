import datetime
import random
import sys
import os
import math
from collections import defaultdict
from dataclasses import dataclass

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.daily_game_simulator import DailyGameSimulator
from src.core.player import Player
from src.core.events import GameEvent, GuessEvent, PowerUpEvent

# --- Configuration ---
SIMULATION_DAYS = 730  # Increased to 2 years for much tighter CIs
PLAYERS_PER_CATEGORY = 10  # Number of players per category
VERBOSE = False
GUESS_ACCURACY = 0.90
ANSWER_WINDOW_MINUTES = 60
FAST_ANSWER_WINDOW_MINUTES = 5  # For Speedsters
LATE_ANSWER_DELAY_HOURS = 6
POWERUP_FAIL_RATE = 0.2  # Chance that powerup is used after target answers
PROACTIVE_MISS_RATE = 0.05  # Chance that proactive shield is forgotten

# --- Difficulty ---
# Each day's question is drawn from one of three tiers.
DIFFICULTY_WEIGHTS = {"Low": 0.35, "Medium": 0.40, "High": 0.25}
DIFFICULTY_VALUES = {"Low": 100, "Medium": 200, "High": 300}
# Additive modifier applied to a player's base guess accuracy per difficulty tier.
# Hard questions are harder to answer correctly; easy questions give a small boost.
DIFFICULTY_ACC_MODIFIER = {"Low": 0.05, "Medium": 0.0, "High": -0.20}

# --- Real Config ---
from src.cfg.main import ConfigReader


class MockQuestion:
    def __init__(self, text, clue_value=100):
        self.text = text
        self.clue_value = clue_value


config = ConfigReader()
REST_MULTIPLIER = float(config.get("JBOT_REST_MULTIPLIER", "1.2"))

# --- Strategies ---


class Strategy:
    def __init__(self, name):
        self.name = name

    def decide_action(self, player_id: str, game_state: "GameState") -> list[GameEvent]:
        raise NotImplementedError

    def _get_guess_text(self):
        # Accuracy configured globally
        return "answer" if random.random() < GUESS_ACCURACY else "wrong"

    def _pick_target_weighted(self, my_id, game_state, weight_func):
        others = [
            p
            for p in game_state.players.values()
            if p.id != my_id and not p.id.startswith("benchmark")
        ]
        if not others:
            return None

        weights = [max(0, weight_func(p)) for p in others]
        total_weight = sum(weights)
        if total_weight == 0:
            return random.choice(others).id

        return random.choices(others, weights=weights, k=1)[0].id

    def _create_powerup_time(self, base_time):
        """
        Determine powerup timestamp.
        Most of the time, it's before the game starts (prepared).
        Sometimes, it's late (simulating human delay/reaction time), potentially after target answers.
        """
        if random.random() < POWERUP_FAIL_RATE:
            # Late usage: Random time within the answer window + buffer
            # This risks being after the target has answered.
            return base_time + datetime.timedelta(
                minutes=random.randint(5, ANSWER_WINDOW_MINUTES + 30)
            )
        else:
            # Early usage: Before game starts
            return base_time - datetime.timedelta(minutes=5)


class BenchmarkStrategy(Strategy):
    def decide_action(self, player_id: str, game_state: "GameState") -> List[GameEvent]:
        # Simple consistent behavior matching global config
        return [self._create_guess(player_id, game_state)]

    def _create_guess(self, player_id, game_state):
        base_time = game_state.base_time
        delta = datetime.timedelta(minutes=random.randint(0, ANSWER_WINDOW_MINUTES))
        timestamp = base_time + delta
        # Use Global Accuracy
        text = "answer" if random.random() < GUESS_ACCURACY else "wrong"
        return GuessEvent(timestamp=timestamp, user_id=player_id, guess_text=text)


class ProceduralStrategy(Strategy):
    def __init__(self, name, speed, correctness, aggression, core_strategy):
        super().__init__(name)
        self.speed = speed  # Fast, Average, Slow
        self.correctness = correctness  # High, Usually, Sometimes
        self.aggression = aggression  # Aggressive, Frequent, Rarely
        self.core_strategy = core_strategy  # Troll, Rester, Thief, Random, Passive

    def decide_action(self, player_id: str, game_state: "GameState") -> List[GameEvent]:
        events = []
        base_time = game_state.base_time
        difficulty = game_state.difficulty

        # 1. Powerup Logic
        # Base probability of using a powerup, scaled per-strategy by difficulty.
        # Rester: much more likely on Hard (risky to guess), less on Easy (free points).
        # Troll/Thief: slightly more active on Hard (bigger bonuses and streaks at risk).
        # Random: unaffected by difficulty.
        if self.core_strategy != "Passive":
            chance_map = {"Aggressive": 0.95, "Frequent": 0.50, "Rarely": 0.10}
            base_chance = chance_map.get(self.aggression, 0.0)
            diff_scale = {
                "Rester": {"Low": 0.50, "Medium": 1.00, "High": 1.60},
                "Troll": {"Low": 0.70, "Medium": 1.00, "High": 1.30},
                "Thief": {"Low": 0.80, "Medium": 1.00, "High": 1.30},
            }.get(self.core_strategy, {"Low": 1.0, "Medium": 1.0, "High": 1.0})
            adjusted_chance = min(1.0, base_chance * diff_scale[difficulty])
            use_powerup = random.random() < adjusted_chance
        else:
            use_powerup = False

        if use_powerup:
            p_type = None
            target = None

            if self.core_strategy == "Rester":
                p_type = "rest"
            elif self.core_strategy == "Troll":
                p_type = "jinx"
                target = self._pick_target_weighted(
                    player_id, game_state, lambda p: p.answer_streak
                )
            elif self.core_strategy == "Thief":
                p_type = "steal"
                target = self._pick_target_weighted(
                    player_id, game_state, lambda p: p.score
                )
            elif self.core_strategy == "Random":
                r = random.random()
                if r < 0.33:
                    p_type = "rest"
                elif r < 0.66:
                    p_type = "jinx"
                    target = self._pick_target_weighted(
                        player_id, game_state, lambda p: p.answer_streak
                    )
                else:
                    p_type = "steal"
                    target = self._pick_target_weighted(
                        player_id, game_state, lambda p: p.score
                    )

            if p_type in ["jinx", "steal"] and not target:
                pass
            else:
                events.append(
                    PowerUpEvent(
                        timestamp=self._create_powerup_time(base_time),
                        user_id=player_id,
                        powerup_type=p_type,
                        target_user_id=target,
                    )
                )
                # Resting players skip guessing for the day
                if p_type == "rest":
                    return events

        # 2. Guess Logic
        events.append(self._create_guess(player_id, game_state))
        return events

    def _create_guess(self, player_id, game_state):
        base_time = game_state.base_time
        difficulty = game_state.difficulty

        # Speed
        if self.speed == "Fast":
            # 0-5 mins
            delta = datetime.timedelta(minutes=random.randint(0, 5))
        elif self.speed == "Slow":
            # 6-12 hours
            delta = datetime.timedelta(minutes=random.randint(360, 720))
        else:  # Average
            delta = datetime.timedelta(minutes=random.randint(0, 60))

        timestamp = base_time + delta

        # Accuracy: player's innate skill ± difficulty modifier
        acc_map = {"Perfect": 1.0, "High": 0.98, "Usually": 0.90, "Sometimes": 0.60}
        acc = min(
            1.0,
            acc_map.get(self.correctness, 0.90) + DIFFICULTY_ACC_MODIFIER[difficulty],
        )
        text = "answer" if random.random() < acc else "wrong"
        return GuessEvent(timestamp=timestamp, user_id=player_id, guess_text=text)


class AdaptiveStrategy(ProceduralStrategy):
    """
    Adapts based on player state, standings, and today's question difficulty:
    - Hard day: rest more eagerly (protect streak, skip risky question)
    - Hard day + low streak: jinx top players rather than steal (bonuses unreliable)
    - Easy/Medium + big streak or near lead: rest to bank multiplier
    - Easy/Medium + low streak: steal to catch up
    - Default: jinx to disrupt opponents
    Overall aggressiveness is dampened on Hard days and boosted on Easy days.
    """

    def decide_action(self, player_id: str, game_state: "GameState") -> List[GameEvent]:
        events = []
        base_time = game_state.base_time
        difficulty = game_state.difficulty

        # Self Analysis
        me = game_state.players[player_id]

        # 1. Determine base aggression from player traits, then scale by difficulty.
        # Hard questions dampen aggression (rest is better). Easy questions raise it.
        base_aggression = 0.3  # Default
        if self.correctness in ["High", "Perfect"] and self.speed == "Fast":
            base_aggression = 0.05
        elif self.correctness == "Sometimes" or self.speed == "Slow":
            base_aggression = 0.75

        diff_aggression_scale = {"Low": 1.30, "Medium": 1.00, "High": 0.65}
        effective_aggression = min(
            0.95, base_aggression * diff_aggression_scale[difficulty]
        )

        if random.random() > effective_aggression:
            # Passive this turn
            return [self._create_guess(player_id, game_state)]

        # 2. Adaptive Choice
        powerup_type = None
        target = None

        # Determine Context
        sorted_scores = [p.score for p in game_state.players.values()]
        max_score = max(sorted_scores) if sorted_scores else 0
        near_lead = me.score >= max_score * 0.95

        # Priority 1: Rest — lower streak threshold on Hard (question is risky to attempt).
        # On Hard, rest if streak >= 2; otherwise the standard threshold applies.
        streak_rest_threshold = 2 if difficulty == "High" else 4
        if (me.answer_streak >= streak_rest_threshold) or near_lead:
            powerup_type = "rest"

        # Priority 2: Steal or Jinx depending on difficulty.
        # On Hard days, bonuses are unreliable (fewer players succeed), so jinx
        # top-streak players instead of gambling on a steal.
        elif me.answer_streak < 2:
            if difficulty == "High":
                powerup_type = "jinx"
                target = self._pick_target_weighted(
                    player_id, game_state, lambda p: p.answer_streak
                )
            else:
                powerup_type = "steal"
                target = self._pick_target_weighted(
                    player_id, game_state, lambda p: p.score
                )

        # Priority 3: Jinx (Default aggressive move)
        else:
            powerup_type = "jinx"
            target = self._pick_target_weighted(
                player_id, game_state, lambda p: p.answer_streak
            )

        if powerup_type:
            if powerup_type == "rest":
                events.append(
                    PowerUpEvent(
                        timestamp=self._create_powerup_time(base_time),
                        user_id=player_id,
                        powerup_type="rest",
                    )
                )
                # Resting players skip guessing for the day
                return events
            elif target:
                events.append(
                    PowerUpEvent(
                        timestamp=self._create_powerup_time(base_time),
                        user_id=player_id,
                        powerup_type=powerup_type,
                        target_user_id=target,
                    )
                )

        events.append(self._create_guess(player_id, game_state))
        return events


# --- Game State Wrapper ---
class GameState:
    def __init__(
        self,
        players: Dict[str, Player],
        base_time: datetime.datetime,
        difficulty: str = "Medium",
    ):
        self.players = players
        self.base_time = base_time
        self.difficulty = (
            difficulty  # "Low", "Medium", or "High" — visible to all strategies
        )


# --- Simulation Engine ---


def run_simulation(return_data=False, seed=None):
    """
    Run the powerup simulation.

    Args:
        return_data: If True, returns (players, player_strategies) dict
        seed: Random seed for reproducibility. If None, uses system randomness.
    """
    if seed is not None:
        random.seed(seed)

    print(f"Starting simulation for {SIMULATION_DAYS} days...")

    players = {}
    player_strategies = {}

    # 1. Benchmark (Control Group)
    for i in range(20):
        pid = f"benchmark_{i+1}"
        players[pid] = Player(id=pid, name=f"Benchmark_{i+1}")
        player_strategies[pid] = BenchmarkStrategy("Benchmark")

    # 1b. The Ideal Player (Validation Check)
    # Passive, Fast, Perfect Accuracy
    pid = "perfect_one"
    players[pid] = Player(id=pid, name="Perfect_Player")
    ps = ProceduralStrategy("Passive", "Fast", "Perfect", "Rarely", "Passive")
    ps.correctness = "Perfect"  # Explicit set
    player_strategies[pid] = ps

    # 1c. Adaptive Players
    # Create a few distinct Adaptive types to see range
    # 1. The Expert (Fast, High Acc) -> Should be mostly passive, maybe shield near end
    for i in range(20):
        pid = f"adaptive_expert_{i+1}"
        players[pid] = Player(id=pid, name=f"Adaptive_Expert_{i+1}")
        player_strategies[pid] = AdaptiveStrategy(
            "Adaptive", "Fast", "High", "Frequent", "Adaptive"
        )

    # 2. The Scrapper (Average, Usually Acc) -> Should steal/jinx to catch up
    for i in range(20):
        pid = f"adaptive_scrapper_{i+1}"
        players[pid] = Player(id=pid, name=f"Adaptive_Scrapper_{i+1}")
        player_strategies[pid] = AdaptiveStrategy(
            "Adaptive", "Average", "Usually", "Frequent", "Adaptive"
        )

    # 3. The Desperate (Slow, Sometimes Acc) -> Should be very aggressive
    for i in range(20):
        pid = f"adaptive_desperate_{i+1}"
        players[pid] = Player(id=pid, name=f"Adaptive_Desperate_{i+1}")
        player_strategies[pid] = AdaptiveStrategy(
            "Adaptive", "Slow", "Sometimes", "Aggressive", "Adaptive"
        )

    # 2. Random Population Coverage
    speeds = ["Fast", "Average", "Slow"]
    corrects = ["High", "Usually", "Sometimes"]
    aggressions = ["Aggressive", "Frequent", "Rarely"]
    cores = ["Troll", "Rester", "Thief", "Random", "Passive"]

    for i in range(1500):  # Increased from 500 to 1500 players
        pid = f"player_{i+1}"

        s = random.choice(speeds)
        c = random.choice(corrects)
        a = random.choice(aggressions)
        core = random.choice(cores)

        # Name convention: Core_Speed_Acc_Agg (Condensed)
        # Actually just maintain Core grouping for the final table
        # We can print their stats in the Name maybe?
        # e.g. "Troll(F,H,A)" -> Fast, High, Aggressive

        short_s = s[0]
        short_c = c[0]
        short_a = a[0]

        p_name = f"{core}_{short_s}{short_c}{short_a}_{i+1}"

        players[pid] = Player(id=pid, name=p_name)
        player_strategies[pid] = ProceduralStrategy(core, s, c, a, core)

    # 2. Daily Loop
    current_date = datetime.date(2024, 1, 1)
    daily_records = []  # Per-day observations for difficulty analysis
    for day in range(SIMULATION_DAYS):
        # New Day Setup
        base_time = datetime.datetime.combine(
            current_date, datetime.time(12, 0)
        )  # Noon
        hint_time = base_time + datetime.timedelta(hours=4)

        # Draw today's difficulty (visible to all players when they decide their action)
        difficulty = random.choices(
            list(DIFFICULTY_WEIGHTS.keys()),
            weights=list(DIFFICULTY_WEIGHTS.values()),
            k=1,
        )[0]
        clue_value = DIFFICULTY_VALUES[difficulty]

        day_events = []
        game_state = GameState(players, base_time, difficulty=difficulty)

        # Players Decide Actions
        for pid, strat in player_strategies.items():
            actions = strat.decide_action(pid, game_state)
            day_events.extend(actions)

        # Determine Correct Answer
        question_answers = ["answer"]

        # Run Simulator
        simulator = DailyGameSimulator(
            question=MockQuestion("What is the answer?", clue_value=clue_value),
            answers=question_answers,
            hint_timestamp=hint_time,
            events=day_events,
            initial_player_states=players,
            config=config,
        )

        daily_results = simulator.run(apply_end_of_day=True)

        # Determine which players rested today
        resting_pids = {
            event.user_id
            for event in day_events
            if isinstance(event, PowerUpEvent) and event.powerup_type == "rest"
        }

        # Update Persistent State
        for pid, result in daily_results.items():
            p = players[pid]

            # Apply (or expire) pending rest multiplier for non-resting players
            if p.pending_rest_multiplier > 1.0 and pid not in resting_pids:
                if result["score_earned"] > 0:
                    bonus = round(
                        result["score_earned"] * (p.pending_rest_multiplier - 1.0)
                    )
                    result["final_score"] += bonus
                p.pending_rest_multiplier = 0.0  # Consumed or expired

            p.score = result["final_score"]
            p.answer_streak = result["final_streak"]

        # Grant next-day multiplier to players who rested today
        for pid in resting_pids:
            if pid in players:
                players[pid].pending_rest_multiplier = REST_MULTIPLIER

        # Record per-day stats for difficulty analysis (sampled every 3rd day)
        if day % 3 == 0:
            for pid, result in daily_results.items():
                strat = player_strategies[pid]
                core = getattr(strat, "core_strategy", strat.name)
                daily_records.append(
                    {
                        "difficulty": difficulty,
                        "core_strategy": core,
                        "score_earned": result["score_earned"],
                        "rested": pid in resting_pids,
                        "correct": result["streak_delta"] > 0,
                    }
                )

        if VERBOSE:
            print(f"Day {day+1} complete.")

        current_date += datetime.timedelta(days=1)

    if return_data:
        return players, player_strategies, daily_records

    # 3. Report
    print("\n--- Final Results (Top 10 Players) ---")
    print(f"{'Strategy':<15} | {'Name':<15} | {'Score':<10} | {'Streak':<10}")
    print("-" * 60)

    # Aggregates
    strat_scores = defaultdict(list)
    speed_scores = defaultdict(list)
    correct_scores = defaultdict(list)
    aggro_scores = defaultdict(list)

    sorted_players = sorted(players.values(), key=lambda p: p.score, reverse=True)

    # Collect stats for all players
    for p in sorted_players:
        s_obj = player_strategies[p.id]
        strat_name = s_obj.name

        if p.id == "perfect_player":
            strat_name = "Perfect"  # Separate bucket

        strat_scores[strat_name].append(p.score)

        # Dimension aggregation (skip Benchmark as it's not procedural)
        if isinstance(s_obj, ProceduralStrategy):
            speed_scores[s_obj.speed].append(p.score)
            correct_scores[s_obj.correctness].append(p.score)
            aggro_scores[s_obj.aggression].append(p.score)

    # Only print top 10 players
    for p in sorted_players[:10]:
        s_obj = player_strategies[p.id]
        strat_name = s_obj.name

        if p.id == "perfect_player":
            strat_name = "Perfect"

        print(
            f"{strat_name:<15} | {p.name:<15} | {p.score:<10} | {p.answer_streak:<10}"
        )

    print("\n--- Performance Ratio by Strategy (vs Benchmark) ---")

    def calculate_stats(scores):
        if not scores:
            return 0.0, 0.0, 0.0
        n = len(scores)
        mean = sum(scores) / n
        if n < 2:
            return mean, 0.0, 0.0
        variance = sum((x - mean) ** 2 for x in scores) / (n - 1)
        std_dev = math.sqrt(variance)
        std_err = std_dev / math.sqrt(n)
        margin_of_error = 1.96 * std_err  # 95% confidence
        return mean, margin_of_error, std_err

    benchmark_mean, benchmark_moe, benchmark_se = 0.0, 0.0, 0.0
    if "Benchmark" in strat_scores:
        benchmark_mean, benchmark_moe, benchmark_se = calculate_stats(
            strat_scores["Benchmark"]
        )

    def print_stats_table(title, data_dict):
        print(f"\n{title}")
        print(f"Benchmark Score: {benchmark_mean:.1f} ± {benchmark_moe:.1f}")
        print("-" * 75)
        print(f"{'Category':<15} | {'Ratio':<18} | {'Avg Score':<15}")
        print("-" * 75)

        stats = []
        for cat, scores in data_dict.items():
            if cat == "Benchmark":
                continue
            mean, moe, se = calculate_stats(scores)

            if benchmark_mean > 0:
                ratio = mean / benchmark_mean
                rel_se_mean = (se / mean) if mean != 0 else 0
                rel_se_bench = benchmark_se / benchmark_mean
                se_ratio = ratio * math.sqrt(rel_se_mean**2 + rel_se_bench**2)
                ratio_moe = 1.96 * se_ratio
            else:
                ratio, ratio_moe = 0.0, 0.0

            stats.append((cat, ratio, ratio_moe, mean, moe))

        # Add Benchmark
        stats.append(("Benchmark", 1.0, 0.0, benchmark_mean, benchmark_moe))

        stats.sort(key=lambda x: x[1], reverse=True)

        for cat, ratio, r_moe, mean, m_moe in stats:
            sig_marker = ""
            if cat != "Benchmark":
                if not (ratio - r_moe <= 1.0 <= ratio + r_moe):
                    sig_marker = "*"
            print(
                f"{cat:<15} : {ratio:.3f} ± {r_moe:.3f}      ({mean:.1f} ± {m_moe:.1f}) {sig_marker}"
            )

    # 1. Strategy
    print_stats_table("--- By Core Strategy ---", strat_scores)

    # 2. Dimensions
    print_stats_table("--- By Answer Speed ---", speed_scores)
    print_stats_table("--- By Correctness ---", correct_scores)
    print_stats_table("--- By Aggression ---", aggro_scores)

    return  # End run

    # Old reporting code below is replaced by function above
    # ...


if __name__ == "__main__":
    run_simulation()
