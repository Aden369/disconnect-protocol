"""Controlled ground-target experiment; actors hold fire to isolate skill effects."""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from thuai10.fourway.game import FourWayGame


def setup(moving=False):
    game = FourWayGame()
    game.entities = [e for e in game.entities if e.type == "hq"]
    game.nodes[0]["owner"] = 0
    game.nodes[1]["owner"] = 1
    observer = game.spawn(0, "dog", (12, 14), slot=0)
    relay = game.spawn(1, "drone", (16, 12), slot=0)
    targets = [
        game.spawn(1, kind, pos, slot=i + 1)
        for i, (kind, pos) in enumerate(
            zip(("dog", "robot", "siege"), ((14, 14), (14, 13), (15, 14)))
        )
    ]
    for entity in [observer, relay, *targets]:
        entity.last_attack = 1000  # No ordinary damage in the control experiment.
        entity.last_move = 1000
    if moving:
        for target in targets:
            target.last_move = -1000
    game.compute_network()
    game.execute(1, 16)  # Existing enemy command to the NE zone.
    game.receive_commands()
    return game, [e.uid for e in targets]


def run():
    base, target_ids = setup()
    rows = []
    for mode in ("control", "missile", "emp", "moving_missile"):
        game = copy.deepcopy(base)
        if mode == "moving_missile":
            game, target_ids = setup(moving=True)
        before = {e.uid: e.hp for e in game.entities if e.uid in target_ids}
        start_linked = sum(uid in game.connected for uid in target_ids)
        start_commanded = sum(
            e.command_until > game.tick for e in game.entities if e.uid in target_ids
        )
        impacts = []
        if "missile" in mode:
            game.step([18, 0, 0, 0])
            result = game.step([27, 0, 0, 0])
            impacts.extend(e for e in result["events"] if e["type"] == "missile_impact")
        else:
            game.step([36 if mode == "emp" else 0, 0, 0, 0])
            game.step([0, 0, 0, 0])
        result = game.step([0, 0, 0, 0])
        impacts.extend(e for e in result["events"] if e["type"] == "missile_impact")
        surviving = {e.uid: e for e in game.entities if e.uid in target_ids}
        rows.append(
            {
                "case": mode,
                "ground_damage": sum(
                    hp - (surviving[uid].hp if uid in surviving else 0)
                    for uid, hp in before.items()
                ),
                "ground_kills": len(before) - len(surviving),
                "linked_before": start_linked,
                "linked_after": sum(uid in game.connected for uid in surviving),
                "commanded_before": start_commanded,
                "commanded_after": sum(
                    e.command_until > game.tick for e in surviving.values()
                ),
                "missile_ground_hits": sum(
                    uid in target_ids for e in impacts for uid in e["hit"]
                ),
                "seconds": game.tick * 0.5,
            }
        )
    return {
        "rules_version": base.cfg["rules_version"],
        "setup": "Three ground targets near (14,14), connected through a support drone. Ordinary attacks disabled; stationary targets hold position except moving_missile.",
        "cases": rows,
    }


if __name__ == "__main__":
    result = run()
    out = Path("results/ground-skills-v0.5.json")
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
