"""对战与 RL review 发现的实际回归场景。"""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from thuai10.core import create_game
from thuai10.core.combat import move_target
from thuai10.core.snapshot import checksum
from thuai10.env.observation import encode_observation, ticks_to_next_decision
from thuai10.server.session import SessionStore, step_session
from thuai10.server.app import CreateGameReq


def attack_game():
    game = create_game()
    for _ in range(3):
        game.step([0, 0])
    return game


def test_watch_calls_each_policy_exactly_once_per_decision():
    class CountingBot:
        def __init__(self): self.calls = 0
        def act(self, state, player, cfg):
            self.calls += 1
            return 0
    _, session = SessionStore().create(mode="watch")
    left, right = CountingBot(), CountingBot()
    session.bots = {"left": left, "right": right}
    step_session(session, None)
    assert left.calls == right.calls == 1


def test_api_defaults_to_four_autonomous_policies():
    req = CreateGameReq()
    assert req.mode == "four" and len(req.policies) == 4
    _, session = SessionStore().create()
    assert session.human_side is None
    assert set(session.bots) == {"left", "right"}


def test_session_seed_is_stable_across_python_hash_seeds():
    code = "from thuai10.server.session import SessionStore, step_session; _,s=SessionStore().create(seed=31,bot_left='random_legal',bot_right='random_legal'); [step_session(s,None) for _ in range(6)]; print(s.game.replay_actions)"
    root = Path(__file__).resolve().parents[1]
    results = []
    for hash_seed in ("1", "42"):
        env = dict(os.environ, PYTHONPATH=str(root / "src"), PYTHONHASHSEED=hash_seed)
        results.append(subprocess.check_output([sys.executable, "-c", code], env=env, cwd=root, text=True))
    assert results[0] == results[1]


def test_produced_units_have_stable_observation_slots():
    game = create_game()
    game.step([20, 21])
    for i, player in enumerate(game.state.players):
        slots = [u.slot for u in player.units]
        assert len(set(slots)) == len(slots)
        assert all(0 <= slot < 12 for slot in slots)
        obs = encode_observation(game.state, i, game.cfg)
        assert obs["units_mask"][0].sum() == len(player.units)


def test_grid_is_in_observer_local_coordinates():
    game = create_game()
    game.step([2, 0])  # left builds an extra barracks; map now asymmetric
    left = encode_observation(game.state, 0, game.cfg)["grid"]
    right = encode_observation(game.state, 1, game.cfg)["grid"]
    assert np.array_equal(left[:, ::-1, 0], right[:, :, 0])
    assert right[5, 1, 4] == 1  # my HQ
    assert right[2, 4, 3] == 1  # my deployment, local x=4


def test_node_progress_actor_and_cannon_cooldown_are_observable():
    game = attack_game()
    game.state.nodes[0].progress = 2
    game.state.nodes[0].progress_player = 0
    a = encode_observation(game.state, 0, game.cfg)
    game.state.nodes[0].progress_player = 1
    b = encode_observation(game.state, 0, game.cfg)
    assert not np.array_equal(a["nodes"], b["nodes"])
    game.state.players[0].slots[3].last_attack_tick = game.state.tick
    c = encode_observation(game.state, 0, game.cfg)
    assert c["buildings"][0, 4, 8] == 1
    assert ticks_to_next_decision(game.state, game.cfg) == 4


def test_unit_mission_does_not_flip_when_node_owner_changes():
    game = attack_game()
    game.step([45, 49])
    dog = next(u for u in game.state.players[0].units if u.on_field)
    robot = next(u for u in game.state.players[1].units if u.on_field)
    assert move_target(game.state, dog, game.cfg) == (8, 2)
    assert move_target(game.state, robot, game.cfg) == (1, 5)
    game.state.nodes[0].owner = 0
    game.state.nodes[1].owner = 1
    assert move_target(game.state, dog, game.cfg) == (8, 2)


def test_signal_temporarily_overrides_then_restores_mission():
    game = attack_game()
    game.step([45, 0])
    dog = next(u for u in game.state.players[0].units if u.on_field)
    player = game.state.players[0]
    player.signal_center = (14, 5)
    player.signal_until_e = 8
    game.state.phase_e = 8
    assert move_target(game.state, dog, game.cfg) == (14, 5)
    game.state.phase_e = 9
    assert move_target(game.state, dog, game.cfg) == (8, 2)


def test_checksum_covers_cooldowns_and_mission():
    game = attack_game()
    before = checksum(game.state, game.cfg)
    game.state.players[0].slots[3].last_attack_tick = game.state.tick
    assert checksum(game.state, game.cfg) != before


def test_target_tiebreak_chronology_is_observable():
    game = create_game()
    a = encode_observation(game.state, 0, game.cfg)
    game.state.players[0].slots[3].birth_tick = 12
    game.state.players[0].units[0].birth_tick = 12
    b = encode_observation(game.state, 0, game.cfg)
    assert not np.array_equal(a["buildings"], b["buildings"])
    assert not np.array_equal(a["units"], b["units"])


def test_tick_frames_include_actual_attacks_and_current_player_state():
    game = attack_game()
    game.step([45, 45])
    out = game.step([0, 0])
    frames = out["frames"]
    assert all(f["players"] and "signals" in f for f in frames)
    assert any(a["kind"] == "attack" and "target_uid" in a for f in frames for a in f["activity"])
