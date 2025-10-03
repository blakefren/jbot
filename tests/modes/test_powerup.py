import pytest
from modes.powerup import PowerUpManager

@pytest.fixture
def players():
    return {
        "1": {"score": 100, "answer_streak": 3},
        "2": {"score": 100, "answer_streak": 5},
        "3": {"score": 10, "answer_streak": 0},
    }

def test_disrupt_basic(players):
    manager = PowerUpManager(players)
    msg = manager.disrupt("1", "2")
    assert "used disrupt" in msg
    assert players["1"]["score"] == 50
    assert players["2"].get("under_attack") is True

def test_disrupt_with_shield(players):
    players["2"]["active_shield"] = True
    manager = PowerUpManager(players)
    msg = manager.disrupt("1", "2")
    assert "shield blocked" in msg
    assert players["2"]["active_shield"] is False
    assert players["1"]["score"] == 50

def test_disrupt_not_enough_points(players):
    players["1"]["score"] = 10
    manager = PowerUpManager(players)
    msg = manager.disrupt("1", "2")
    assert "Not enough points" in msg

def test_use_shield_basic(players):
    manager = PowerUpManager(players)
    msg = manager.use_shield("1")
    assert "activated a shield" in msg
    assert players["1"]["active_shield"] is True
    assert players["1"]["score"] == 75

def test_use_shield_already_active(players):
    players["1"]["active_shield"] = True
    manager = PowerUpManager(players)
    msg = manager.use_shield("1")
    assert "already active" in msg

def test_use_shield_not_enough_points(players):
    players["1"]["score"] = 10
    manager = PowerUpManager(players)
    msg = manager.use_shield("1")
    assert "Not enough points" in msg

def test_wager_points_basic(players):
    manager = PowerUpManager(players)
    msg = manager.wager_points("1", 10)
    assert "wager 10 points" in msg
    assert players["1"]["score"] == 90
    assert players["1"]["wager"] == 10

def test_wager_points_max_wager(players):
    manager = PowerUpManager(players)
    msg = manager.wager_points("1", 100)
    assert "wager 25 points" in msg  # 100//4 = 25
    assert players["1"]["score"] == 75
    assert players["1"]["wager"] == 25

def test_wager_points_invalid(players):
    manager = PowerUpManager(players)
    msg = manager.wager_points("1", 0)
    assert "Invalid wager amount" in msg
    msg2 = manager.wager_points("1", 200)
    assert "Invalid wager amount" in msg2

def test_resolve_wager_win(players):
    manager = PowerUpManager(players)
    manager.wager_points("1", 20)
    msg = manager.resolve_wager("1", True)
    assert "won the wager" in msg
    assert players["1"]["wager"] == 0

def test_resolve_wager_lose(players):
    manager = PowerUpManager(players)
    manager.wager_points("1", 20)
    msg = manager.resolve_wager("1", False)
    assert "lost the wager" in msg
    assert players["1"]["wager"] == 0

def test_resolve_wager_attack(players):
    manager = PowerUpManager(players)
    players["1"]["under_attack"] = True
    msg = manager.resolve_wager("1", False)
    assert "Streak reset" in msg
    players["1"]["under_attack"] = True
    msg2 = manager.resolve_wager("1", True)
    assert "Streak preserved" in msg2

def test_reinforce_success(players):
    manager = PowerUpManager(players)
    msg = manager.reinforce("1", "2")
    assert "reinforced" in msg
    assert players["1"]["score"] == 75
    assert players["2"]["score"] == 75
    assert players["1"]["team_partner"] == "2"
    assert players["2"]["team_partner"] == "1"

def test_reinforce_already_teamed(players):
    players["1"]["team_partner"] = "2"
    manager = PowerUpManager(players)
    msg = manager.reinforce("1", "2")
    assert "already teamed up" in msg

def test_reinforce_not_enough_points(players):
    players["1"]["score"] = 10
    manager = PowerUpManager(players)
    msg = manager.reinforce("1", "2")
    assert "need at least 25 points" in msg

def test_reinforce_invalid_player(players):
    manager = PowerUpManager(players)
    msg = manager.reinforce("1", "999")
    assert "Invalid player" in msg

def test_resolve_reinforce(players):
    manager = PowerUpManager(players)
    manager.reinforce("1", "2")
    msg = manager.resolve_reinforce("1", True)
    assert "both get full points" in msg or msg == ""

def test_steal_success(players):
    players["2"]["earned_today"] = 40
    manager = PowerUpManager(players)
    msg = manager.steal("1", "2")
    assert "stole 20 points" in msg
    assert players["1"]["score"] == 120
    assert players["2"]["score"] == 80
    assert players["2"]["earned_today"] == 20

def test_steal_no_points(players):
    players["2"]["earned_today"] = 0
    manager = PowerUpManager(players)
    msg = manager.steal("1", "2")
    assert "no points to steal" in msg

def test_steal_invalid_player(players):
    manager = PowerUpManager(players)
    msg = manager.steal("1", "999")
    assert "Invalid player" in msg
