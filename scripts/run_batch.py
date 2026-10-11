"""批量对战与统计。

用法：
    PYTHONPATH=src python scripts/run_batch.py --mode bots --games 5 --out results/bot-matchups.json
    PYTHONPATH=src python scripts/run_batch.py --mode random --games 100 --out results/random-games.json

--mode bots：四种脚本两两对战并换边（六组），每组每边 --games 个 seed。
--mode random：随机合法对战（有种子的探索轨迹）。
统计：胜负/平局、总部摧毁率、超时率、平均及 P95 模拟局长、节点易主次数、
各兵种生产与死亡、资源花费构成。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thuai10.bots import SCRIPT_BOTS, make_bot  # noqa: E402
from thuai10.core import create_game  # noqa: E402

SPEND_EVENTS = {
    "build": {"barracks": 70, "cannon": 60, "shield": 50},
    "tech": 60,
    "repair": 20,
    "signal": 5,
    "bomb": 30,
}
UNIT_PRICE = {"dog": 20, "robot": 35, "siege": 55}


def play_game(seed: int, bot0: str, bot1: str) -> dict:
    game = create_game(seed=seed)
    b0 = make_bot(bot0, seed=seed * 2 + 1)
    b1 = make_bot(bot1, seed=seed * 2 + 2)
    produced = [defaultdict(int), defaultdict(int)]
    deaths = [defaultdict(int), defaultdict(int)]
    spend = [defaultdict(int), defaultdict(int)]
    node_flips = 0
    while not game.state.over:
        st = game.state
        out = game.step([b0.act(st, 0, game.cfg), b1.act(st, 1, game.cfg)])
        for ev in out["events"]:
            if ev["type"] == "produce":
                produced[ev["player"]][ev["unit"]] += ev["count"]
                spend[ev["player"]]["produce"] += ev["count"] * UNIT_PRICE[ev["unit"]]
            elif ev["type"] == "unit_death":
                deaths[ev["player"]][ev["unit"]] += 1
            elif ev["type"] == "node_flip":
                node_flips += 1
            elif ev["type"] == "build":
                spend[ev["player"]]["build"] += SPEND_EVENTS["build"][ev["building"]]
            elif ev["type"] in ("tech", "repair", "signal", "bomb"):
                spend[ev["player"]][ev["type"]] += SPEND_EVENTS[ev["type"]]
    st = game.state
    return {
        "seed": seed,
        "p0": bot0,
        "p1": bot1,
        "winner": st.winner,
        "end_reason": st.end_reason,
        "ticks": st.tick,
        "sim_seconds": st.tick * 0.5,
        "hq_hp": [p.hq.hp for p in st.players],
        "scores": game.scores(),
        "control_seconds": [p.control_ticks * 0.5 for p in st.players],
        "node_flips": node_flips,
        "produced": [dict(produced[0]), dict(produced[1])],
        "deaths": [dict(deaths[0]), dict(deaths[1])],
        "spend": [dict(spend[0]), dict(spend[1])],
    }


def percentile(values, p):
    if not values:
        return 0
    vs = sorted(values)
    k = max(0, min(len(vs) - 1, int(round((len(vs) - 1) * p))))
    return vs[k]


def summarize(games: list[dict]) -> dict:
    n = len(games)
    wins = [0, 0, 0]  # p0 / p1 / draw
    hq_destroyed = 0
    durations = []
    flips = []
    produced = [defaultdict(int), defaultdict(int)]
    deaths = [defaultdict(int), defaultdict(int)]
    spend = [defaultdict(int), defaultdict(int)]
    for g in games:
        wins[g["winner"] if g["winner"] in (0, 1) else 2] += 1
        if g["end_reason"] == "hq_destroyed":
            hq_destroyed += 1
        durations.append(g["sim_seconds"])
        flips.append(g["node_flips"])
        for i in (0, 1):
            for k, v in g["produced"][i].items():
                produced[i][k] += v
            for k, v in g["deaths"][i].items():
                deaths[i][k] += v
            for k, v in g["spend"][i].items():
                spend[i][k] += v
    return {
        "games": n,
        "wins_p0": wins[0],
        "wins_p1": wins[1],
        "draws": wins[2],
        "hq_destroyed_rate": hq_destroyed / n if n else 0,
        "timeout_rate": 1 - hq_destroyed / n if n else 0,
        "avg_sim_seconds": statistics.mean(durations) if durations else 0,
        "p95_sim_seconds": percentile(durations, 0.95),
        "avg_node_flips": statistics.mean(flips) if flips else 0,
        "produced": [dict(produced[0]), dict(produced[1])],
        "deaths": [dict(deaths[0]), dict(deaths[1])],
        "spend": [dict(spend[0]), dict(spend[1])],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("bots", "random"), default="bots")
    ap.add_argument("--games", type=int, default=5, help="bots: 每组每边局数；random: 总局数")
    ap.add_argument("--out", default="results/batch.json")
    ap.add_argument("--seeds-from", type=int, default=0)
    args = ap.parse_args()

    games: list[dict] = []
    t0 = time.perf_counter()
    if args.mode == "bots":
        pairs = [
            (a, b) for i, a in enumerate(SCRIPT_BOTS) for b in SCRIPT_BOTS[i + 1 :]
        ]
        for a, b in pairs:
            for swap in (False, True):
                n0, n1 = (b, a) if swap else (a, b)
                for k in range(args.games):
                    seed = args.seeds_from + k
                    g = play_game(seed, n0, n1)
                    g["pair"] = f"{a} vs {b}"
                    g["swap"] = swap
                    games.append(g)
                    print(
                        f"[{len(games)}] {n0:12s} vs {n1:12s} seed={seed} "
                        f"winner={g['winner']} reason={g['end_reason']} t={g['sim_seconds']}s",
                        flush=True,
                    )
    else:
        for k in range(args.games):
            seed = args.seeds_from + k
            g = play_game(seed, "random_legal", "random_legal")
            games.append(g)
            if (k + 1) % 10 == 0:
                print(f"[{k + 1}/{args.games}] random games done", flush=True)

    elapsed = time.perf_counter() - t0
    result = {
        "mode": args.mode,
        "games": games,
        "summary": summarize(games),
        "wall_seconds": elapsed,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"共 {len(games)} 局，用时 {elapsed:.1f}s，写入 {out}")
    if args.mode == "random":
        finished = sum(1 for g in games if g["winner"] is not None or g["end_reason"])
        print(f"全部结束检查：{finished}/{len(games)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
