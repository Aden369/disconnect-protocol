"""无界面基准：记录每秒 tick 与整局耗时（注明机器环境，不承诺吞吐指标）。"""
from __future__ import annotations

import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thuai10.bots import make_bot  # noqa: E402
from thuai10.core import create_game  # noqa: E402


def run_game(seed: int) -> tuple[float, int]:
    game = create_game(seed=seed)
    b0 = make_bot("robot_push", seed=seed)
    b1 = make_bot("node_grabber", seed=seed + 1)
    t0 = time.perf_counter()
    while not game.state.over:
        st = game.state
        game.step([b0.act(st, 0, game.cfg), b1.act(st, 1, game.cfg)])
    return time.perf_counter() - t0, game.state.tick


def main() -> int:
    print(f"环境: Python {platform.python_version()} on {platform.platform()}")
    print(f"处理器: {platform.processor() or 'unknown'}")
    times, ticks = [], 0
    for seed in range(10):
        dt, n = run_game(seed)
        times.append(dt)
        ticks += n
        print(f"  seed={seed}: {dt:.3f}s / {n} ticks ({n / dt:.0f} ticks/s)")
    total = sum(times)
    print(f"平均整局 {statistics.mean(times):.3f}s，合计 {ticks} ticks，{ticks / total:.0f} ticks/s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
