"""回放一致性：同动作序列回放状态哈希完全一致，篡改即失败。"""
from __future__ import annotations

import json

from thuai10.core import create_game
from thuai10.core.replay import record, verify
from thuai10.bots import make_bot


def _play(seed=5, steps=40):
    game = create_game(seed=seed)
    b0 = make_bot("node_grabber", seed=1)
    b1 = make_bot("robot_push", seed=2)
    for _ in range(steps):
        if game.state.over:
            break
        st = game.state
        game.step([b0.act(st, 0, game.cfg), b1.act(st, 1, game.cfg)])
    return game


def test_replay_roundtrip_identical():
    game = _play()
    replay = record(game)
    assert replay["schema_version"] == game.cfg.schema_version
    assert replay["rules_version"] == game.cfg.rules_version
    result = verify(replay)
    assert result["ok"], result
    assert result["winner"] == game.state.winner


def test_replay_tamper_detected():
    game = _play()
    replay = record(game)
    bad = json.loads(json.dumps(replay))
    bad["actions"][3][0] = (bad["actions"][3][0] + 1) % 72
    result = verify(bad)
    assert not result["ok"]


def test_replay_deterministic_across_instances():
    g1 = _play(seed=9, steps=30)
    g2 = _play(seed=9, steps=30)
    r1, r2 = record(g1), record(g2)
    assert r1["actions"] == r2["actions"]
    assert r1["checks"] == r2["checks"], "同 seed 同策略：状态校验值逐决策一致"


def test_same_seed_same_replay():
    """确定性验收：同 seed 同动作 → 同结果。"""
    game = create_game(seed=3)
    acts = [[20, 2], [0, 0], [0, 0], [45, 45]] + [[0, 0]] * 20
    for a in acts:
        if game.state.over:
            break
        game.step(a)
    snap1 = game.snapshot()

    game2 = create_game(seed=3)
    for a in acts:
        if game2.state.over:
            break
        game2.step(a)
    snap2 = game2.snapshot()
    assert snap1 == snap2
