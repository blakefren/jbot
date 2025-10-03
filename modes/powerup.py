"""
POWERUP mode logic for jbot trivia game.
Implements power-up actions: attack, shield, and bet.
"""

from typing import Dict

class PowerUpManager:
    """
    Manages power-up actions for POWERUP game mode, including attacking streaks, using shields, and betting points.
    """

    def __init__(self, players: Dict[str, dict]):
        """
        Initialize the PowerUpManager.
        Args:
            players (Dict[str, dict]): Dictionary of player data keyed by player ID.
        """
        self.players = players

    def reinforce(self, player1_id: str, player2_id: str) -> str:
        """
        Team up two players for a cost of 25 points each. If either is correct, both get full points for the day.
        Args:
            player1_id (str): The ID of the first player.
            player2_id (str): The ID of the second player.
        Returns:
            str: Result message of the team up action.
        """
        p1 = self.players.get(player1_id)
        p2 = self.players.get(player2_id)
        if not p1 or not p2:
            return "Invalid player(s)."
        if p1.get("score", 0) < 25 or p2.get("score", 0) < 25:
            return "Both players need at least 25 points to team up."
        if p1.get("team_partner") or p2.get("team_partner"):
            return "One or both players are already teamed up today."
        p1["score"] -= 25
        p2["score"] -= 25
        p1["team_partner"] = player2_id
        p2["team_partner"] = player1_id
        return f"{player1_id} and {player2_id} are now teamed up! If either answers correctly, both get full points."

    def resolve_reinforce(self, player_id: str, correct: bool) -> str:
        """
        Resolve team up effect after a player's answer. If either partner is correct, both get full points for the day.
        Args:
            player_id (str): The ID of the player whose answer is being resolved.
            correct (bool): Whether the player's answer was correct.
        Returns:
            str: Result message of the team up resolution.
        """
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
            msg = f"Team up: {player_id} and {partner_id} both get full points for today!"
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
        Break another player's answer streak. Costs 50 points. If the target has an active shield, the shield is broken instead (shield only protects once per day). If the target answers correctly that day, their streak is not reset.
        Args:
            attacker_id (str): The ID of the attacking player.
            target_id (str): The ID of the target player.
        Returns:
            str: Result message of the streak breaker action.
        """
        attacker = self.players.get(attacker_id)
        target = self.players.get(target_id)
        if not attacker or not target:
            return "Invalid player(s)."
        if attacker.get("score", 0) < 50:
            return "Not enough points to use streak breaker (need 50)."
        attacker["score"] -= 50
        if target.get("active_shield", False):
            target["active_shield"] = False
            return f"{target_id}'s shield blocked the streak breaker! Shield is now broken."
        # Mark that target is under attack for this day
        target["under_attack"] = True
        return f"{attacker_id} used streak breaker on {target_id}! If {target_id} gets today's answer wrong, their streak will be reset."

    def use_shield(self, player_id: str) -> str:
        """
        Activate a shield for the player, blocking the next attack (once per day). Costs 25 points.
        Args:
            player_id (str): The ID of the player using a shield.
        Returns:
            str: Result message of the shield action.
        """
        player = self.players.get(player_id)
        if not player:
            return "Invalid player."
        if player.get("active_shield", False):
            return "Shield already active."
        if player.get("score", 0) < 25:
            return "Not enough points to activate shield (need 25)."
        player["score"] -= 25
        player["active_shield"] = True
        return f"{player_id} activated a shield!"

    def wager_points(self, player_id: str, amount: int) -> str:
        """
        Place a bet with points for the current question. Bet is capped at 25% of current score (min 1 point).
        Args:
            player_id (str): The ID of the player betting points.
            amount (int): The number of points to bet.
        Returns:
            str: Result message of the bet action.
        """
        player = self.players.get(player_id)
        if not player:
            return "Invalid player."
        score = player.get("score", 0)
        max_bet = max(1, score // 4)
        if amount <= 0 or amount > score:
            return f"Invalid bet amount."
        final_bet = min(amount, max_bet)
        player["score"] -= final_bet
        player["bet"] = final_bet
        return f"{player_id} bet {final_bet} points! (Max allowed: {max_bet})"

    def resolve_wager(self, player_id: str, correct: bool) -> str:
        """
        Resolve a player's bet after answering a question. Also resolves attack effect if player was attacked. Winning returns diminishing returns. If attacked and incorrect, streak is reset.
        Args:
            player_id (str): The ID of the player whose bet is being resolved.
            correct (bool): Whether the player's answer was correct.
        Returns:
            str: Result message of the bet resolution.
        """
        player = self.players.get(player_id)
        bet = player.get("bet", 0)
        msg = ""
        if bet != 0:
            if correct:
                score = player.get("score", 0)
                winnings = int(bet * (100 / (score + 100)))
                player["score"] += winnings
                msg += f"{player_id} won the bet and now has {player['score']} points! (Winnings: {winnings})\n"
            else:
                msg += f"{player_id} lost the bet.\n"
            player["bet"] = 0
        # Handle attack effect
        if player.get("under_attack", False):
            if not correct:
                player["answer_streak"] = 0
                msg += f"{player_id} was attacked and got the answer wrong. Streak reset!"
            else:
                msg += f"{player_id} was attacked but got the answer right. Streak preserved!"
            player["under_attack"] = False
        return msg.strip()

    def weekly_boss_fight(self, player_id: str) -> str:
        """
        Engage in a weekly boss fight. Not implemented yet.
        Args:
            player_id (str): The ID of the player engaging in the boss fight.
        Returns:
            str: Result message of the boss fight action.
        """
        return "Not implemented"

    def reveal_answer_letters(self, player_id: str) -> str:
        """
        Reveal the letters of the correct answer. Not implemented yet.
        Args:
            player_id (str): The ID of the player revealing answer letters.
        Returns:
            str: Result message of the reveal answer letters action.
        """
        return "Not implemented"

    def red_vs_blue_teams(self, player_id: str) -> str:
        """
        Participate in red vs blue teams activity. Not implemented yet.
        Args:
            player_id (str): The ID of the player participating in the teams activity.
        Returns:
            str: Result message of the red vs blue teams action.
        """
        return "Not implemented"
