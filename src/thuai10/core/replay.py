"""回放：保存规则/schema 版本、配置、seed、双方动作序列和关键状态校验值。

校验回放一致性：
    PYTHONPATH=src python -m thuai10.core.replay results/replay-example.json
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .config import BalanceConfig
from .engine import Game


def record(game: Game, meta: dict[str, Any] | None = None) -> dict:
    """将一局已结束（或进行中）的对局导出为回放 JSON 结构。"""
    return {
        "schema_version": game.cfg.schema_version,
        "rules_version": game.cfg.rules_version,
        "config_version": game.cfg.version,
        "config": game.cfg.raw,
        "seed": game.seed,
        "actions": game.replay_actions,
        "checks": game.replay_checks,
        "final": {
            "winner": game.state.winner,
            "end_reason": game.state.end_reason,
            "steps": game.state.steps_taken,
            "ticks": game.state.tick,
            "scores": game.scores(),
        },
        "meta": meta or {},
    }


def verify(replay: dict) -> dict:
    """按动作序列重放，校验每一步状态哈希与终局一致。"""
    if replay.get("rules_version") in (
        "game-rules-v0.3",
        "game-rules-v0.4",
        "game-rules-v0.5",
        "game-rules-v0.6",
    ):
        from thuai10.fourway.game import verify_replay

        return verify_replay(replay)
    cfg = BalanceConfig(replay["config"])
    game = Game(cfg, seed=replay.get("seed", 0))
    for i, (a0, a1) in enumerate(replay["actions"]):
        game.step([a0, a1])
        expected = replay["checks"][i]
        actual = game.replay_checks[i]
        if expected != actual:
            return {
                "ok": False,
                "failed_step": i,
                "expected": expected,
                "actual": actual,
            }
    final = replay.get("final", {})
    ok = game.state.winner == final.get(
        "winner"
    ) and game.state.end_reason == final.get("end_reason")
    return {"ok": ok, "steps": game.state.steps_taken, "winner": game.state.winner}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: python -m thuai10.core.replay <replay.json>")
        return 2
    with open(argv[0], encoding="utf-8") as f:
        replay = json.load(f)
    result = verify(replay)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
