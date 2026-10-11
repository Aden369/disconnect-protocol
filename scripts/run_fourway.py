"""四方验证：24 个策略排列或有种子的随机合法对战。"""

import argparse
import itertools
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from thuai10.fourway.game import FourWayGame
from thuai10.fourway.policies import POLICIES, Policy, RandomPolicy


def play(seed, names):
    game = FourWayGame(seed)
    bots = [
        RandomPolicy(seed * 100 + i)
        if name == "random"
        else Policy(name, seed + i * 1000)
        for i, name in enumerate(names)
    ]
    counts = Counter()
    while not game.over:
        actions = [bot.act(game, i) for i, bot in enumerate(bots)]
        types = {e.uid: e.type for e in game.entities}
        counts["ground_skill_decisions"] += sum(
            bool(getattr(bot, "last_reason", "")) for bot in bots
        )
        out = game.step(actions)
        for event in out["events"]:
            if event["type"] == "missile_impact":
                counts["missile_ground_hits"] += sum(
                    types.get(uid) in ("dog", "robot", "siege") for uid in event["hit"]
                )
                counts["missile_structure_hits"] += sum(
                    types.get(uid)
                    in ("hq", "wall", "cannon", "mortar", "antiair", "jammer")
                    for uid in event["hit"]
                )
        counts.update(e["type"] for e in out["events"])
        assert game.steps <= 90 and game.tick <= 360
        assert all(0 <= p.resources <= game.cfg["economy"]["cap"] for p in game.players)
        assert all(len(game.units(i)) <= 12 for i in range(4))
    return {
        "seed": seed,
        "policies": names,
        "winner": game.winner,
        "reason": game.end_reason,
        "seconds": game.tick * 0.5,
        "hq_hp": [game.headquarters(i).hp for i in range(4)],
        "eliminated_ticks": [p.eliminated_tick for p in game.players],
        "events": dict(counts),
    }, game


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["scripts", "random"], default="scripts")
    parser.add_argument("--games", type=int, default=24)
    parser.add_argument("--out", default="results/fourway-scripts-v0.5.json")
    parser.add_argument("--replay-out", default="results/fourway-replay-v0.5.json")
    args = parser.parse_args()
    permutations = list(itertools.permutations(POLICIES))
    rows = []
    started = time.perf_counter()
    for i in range(args.games):
        names = (
            ["random"] * 4
            if args.mode == "random"
            else list(permutations[i % len(permutations)])
        )
        row, game = play(i, names)
        rows.append(row)
        if i == 0 and args.mode == "scripts":
            replay_path = Path(args.replay_out)
            replay_path.parent.mkdir(parents=True, exist_ok=True)
            replay_path.write_text(
                json.dumps(
                    game.replay({"policies": names}), ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
        if (i + 1) % 5 == 0 or i == args.games - 1:
            print(f"{i + 1}/{args.games} completed", flush=True)
    wins = Counter(row["policies"][row["winner"]] for row in rows if row["winner"] >= 0)
    events = Counter()
    for row in rows:
        events.update(row["events"])
    summary = {
        "games": len(rows),
        "completed": sum(row["reason"] is not None for row in rows),
        "champions_by_policy": dict(wins),
        "draws": sum(row["winner"] < 0 for row in rows),
        "average_seconds": statistics.mean(row["seconds"] for row in rows),
        "max_seconds": max(row["seconds"] for row in rows),
        "events": dict(events),
        "wall_seconds": time.perf_counter() - started,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "rules_version": "game-rules-v0.5",
                "mode": args.mode,
                "summary": summary,
                "games": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
