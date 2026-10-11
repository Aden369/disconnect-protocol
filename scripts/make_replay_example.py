"""生成回放示例 results/replay-example.json 并当场校验。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thuai10.bots import make_bot  # noqa: E402
from thuai10.core import create_game  # noqa: E402
from thuai10.core.replay import record, verify  # noqa: E402


def main() -> int:
    game = create_game(seed=2026)
    b0 = make_bot("node_grabber", seed=1)
    b1 = make_bot("robot_push", seed=2)
    while not game.state.over:
        st = game.state
        game.step([b0.act(st, 0, game.cfg), b1.act(st, 1, game.cfg)])
    replay = record(
        game,
        meta={"description": "node_grabber vs robot_push 示范回放", "generator": "scripts/make_replay_example.py"},
    )
    out = Path("results/replay-example.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")
    result = verify(replay)
    print(json.dumps(result, ensure_ascii=False))
    print(f"写入 {out}（{len(replay['actions'])} 步）")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
