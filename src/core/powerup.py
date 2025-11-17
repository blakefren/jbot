"""
POWERUP mode logic for jbot trivia game.
Implements power-up actions: attack, shield, and wager.
"""

from typing import Dict
from src.cfg.main import ConfigReader
from src.core.base_manager import BaseManager

config = ConfigReader()


class PowerUpManager(BaseManager):
    """
    Manages power-up actions for POWERUP game mode, including attacking streaks,
    using shields, and wagering points.
    """

    def __init__(self, players: Dict[str, dict]):
        """
        Initialize the PowerUpManager.
        Args:
            players (Dict[str, dict]): Dictionary of player data keyed by player ID.
        """
        self.players = players

    def on_guess(self, player_id: int, player_name: str, guess: str, is_correct: bool):
        self.resolve_wager(str(player_id), is_correct)

    def reinforce(self, player1_id: str, player2_id: str) -> str:
        """
        Team up two players for a cost of 25 points each. If either is correct,
        both get full points for the day.
        Args:
            player1_id (str): The ID of the first player.
            player2_id (str): The ID of the second player.
        Returns:
            str: Result message of the team up action.
        """
        # TODO: Migrate to PlayerManager
        p1 = self.players.get(player1_id)
        p2 = self.players.get(player2_id)
        if not p1 or not p2:
            return "Invalid player(s)."

        cost = int(config.get("JBOT_REINFORCE_COST", 25))
        if p1.get("score", 0) < cost or p2.get("score", 0) < cost:
            return f"Both players need at least {cost} points to team up."
        if p1.get("team_partner") or p2.get("team_partner"):
            return "One or both players are already teamed up today."
        p1["score"] -= cost
        p2["score"] -= cost
        p1["team_partner"] = player2_id
        p2["team_partner"] = player1_id
        return (
            f"{player1_id} and {player2_id} are now teamed up! "
            "If either answers correctly, both get full points."
        )

    def resolve_reinforce(self, player_id: str, correct: bool) -> str:
        """
        Resolve team up effect after a player's answer. If either partner is correct,
        both get full points for the day.
        Args:
            player_id (str): The ID of the player whose answer is being resolved.
            correct (bool): Whether the player's answer was correct.
        Returns:
            str: Result message of the team up resolution.
        """
        # TODO: Migrate to PlayerManager
        player = self.players.get(player_id)
        partner_id = player.get("team_partner")
        if not partner_id:
            return ""
        partner = self.players.get(partner_id)
        msg = ""
        if correct:
            player["team_success"] = True
            if partner:
                partner["team_success"] = True
        # After both have answered, resolve points
        if player.get("team_success") or (partner and partner.get("team_success")):
            msg = (
                f"Team up: {player_id} and {partner_id} both get full points for today!"
            )
            player["team_success"] = False
            if partner:
                partner["team_success"] = False
            player["team_partner"] = None
            if partner:
                partner["team_partner"] = None
        return msg

    def steal(self, thief_id: str, target_id: str) -> str:
        """
        Steal half of another player's earned points for the day.
        Args:
            thief_id (str): The ID of the player stealing.
            target_id (str): The ID of the player being stolen from.
        Returns:
            str: Result message of the steal action.
        """
        # TODO: Migrate to PlayerManager
        thief = self.players.get(thief_id)
        target = self.players.get(target_id)
        if not thief or not target:
            return "Invalid player(s)."
        earned_today = target.get("earned_today", 0)
        if earned_today <= 0:
            return f"{target_id} has no points to steal today."
        stolen = earned_today // 2
        target["score"] -= stolen
        thief["score"] += stolen
        target["earned_today"] -= stolen
        return f"{thief_id} stole {stolen} points from {target_id}!"

    def disrupt(self, attacker_id: str, target_id: str) -> str:
        """
        Break another player's answer streak. Costs 50 points.
        If the target has an active shield, the shield is broken instead.
        If the target answers correctly that day, their streak is not reset.
        Args:
            attacker_id (str): The ID of the attacking player.
            target_id (str): The ID of the target player.
        Returns:
            str: Result message of the disrupt action.
        """
        # TODO: Migrate to PlayerManager
        attacker = self.players.get(attacker_id)
        target = self.players.get(target_id)
        if not attacker or not target:
            return "Invalid player(s)."

        cost = int(config.get("JBOT_DISRUPT_COST", 50))
        if attacker.get("score", 0) < cost:
            return f"Not enough points to use disrupt (need {cost})."
        attacker["score"] -= cost
        if target.get("active_shield", False):
            target["active_shield"] = False
            return f"{target_id}'s shield blocked the disrupt! " "Shield is now broken."
        # Mark that target is under attack for this day
        target["under_attack"] = True
        return (
            f"{attacker_id} used disrupt on {target_id}! "
            f"If {target_id} gets today's answer wrong, their streak will be reset."
        )

    def use_shield(self, player_id: str) -> str:
        """
        Activate a shield for the player, blocking the next attack. Costs 25 points.
        Args:
            player_id (str): The ID of the player using a shield.
        Returns:
            str: Result message of the shield action.
        """
        # TODO: Migrate to PlayerManager
        player = self.players.get(player_id)
        if not player:
            return "Invalid player."
        if player.get("active_shield", False):
            return "Shield already active."

        cost = int(config.get("JBOT_SHIELD_COST", 25))
        if player.get("score", 0) < cost:
            return f"Not enough points to activate shield (need {cost})."
        player["score"] -= cost
        player["active_shield"] = True
        return f"{player_id} activated a shield!"

    def place_wager(self, player_id: str, amount: int) -> str:
        """
        Place a wager with points for the current question.
        Wager is capped at 25% of current score (min 1 point).
        Args:
            player_id (str): The ID of the player wagering points.
            amount (int): The number of points to wager.
        Returns:
            str: Result message of the wager action.
        """
        # TODO: Migrate to PlayerManager
        player = self.players.get(player_id)
        if not player:
            return "Invalid player."
        score = player.get("score", 0)

        # TODO: play with the percentage cap
        cap_percentage = int(config.get("JBOT_WAGER_CAP_PERCENTAGE", 25))
        max_wager = max(1, score // (100 // cap_percentage))
        if amount <= 0 or amount > score:
            return "Invalid wager amount."
        final_wager = min(amount, max_wager)
        player["score"] -= final_wager
        player["wager"] = final_wager
        return f"{player_id} wagered {final_wager} points! (Max allowed: {max_wager})"

    def resolve_wager(self, player_id: str, correct: bool) -> str:
        """
        Resolve a player's wager after answering a question.
        Also resolves attack effect if player was attacked.
        Winning returns diminishing returns.
        If attacked and incorrect, streak is reset.
        Args:
            player_id (str): The ID of the player whose wager is being resolved.
            correct (bool): Whether the player's answer was correct.
        Returns:
            str: Result message of the wager resolution.
        """
        # TODO: Migrate to PlayerManager
        player = self.players.get(player_id)
        wager = player.get("wager", 0)
        msg = ""
        if wager != 0:
            if correct:
                score = player.get("score", 0)
                winnings = int(wager * (100 / (score + 100)))
                player["score"] += winnings
                msg += (
                    f"{player_id} won the wager and now has {player['score']} points! "
                    f"(Winnings: {winnings})\n"
                )
            else:
                msg += f"{player_id} lost the wager.\n"
            player["wager"] = 0
        # Handle attack effect
        if player.get("under_attack", False):
            if not correct:
                player["answer_streak"] = 0
                msg += (
                    f"{player_id} was attacked and got the answer wrong. Streak reset!"
                )
            else:
                msg += (
                    f"{player_id} was attacked but got the answer right. "
                    "Streak preserved!"
                )
            player["under_attack"] = False
        return msg.strip()
