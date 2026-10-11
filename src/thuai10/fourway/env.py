"""固定四方观测；全信息世界坐标，观察者编号单独编码。"""

from typing import ClassVar

import numpy as np

from .game import SIDES, UNIT_TYPES, FourWayGame

SHAPES = {
    "public": (5,),
    "companies": (4, 12),
    "units": (4, 12, 20),
    "structures": (4, 38, 10),
    "nodes": (4, 7),
    "signals": (4, 6),
    "clouds": (4, 6),
    "projectiles": (4, 2, 9),
}
SCHEMA = "thuai10-fourway-obs-v0.5"


def observe(game, player):
    shapes = dict(SHAPES)
    modern = "initial_buildings" in game.cfg["map"]
    if not modern:
        shapes["structures"] = (4, 21, 10)
    arrays = {k: np.zeros(shape, dtype=np.float32) for k, shape in shapes.items()}
    scale = game.cfg["map"]["size"] - 1
    arrays["public"][:] = (
        player / 3,
        game.tick / game.cfg["time"]["max_ticks"],
        game.steps / 90,
        float(game.tick >= game.cfg["time"]["overload_tick"]),
        game.next_uid / 10000,
    )
    for p in game.players:
        arrays["companies"][p.index] = (
            float(p.alive),
            p.resources / game.cfg["economy"]["cap"],
            p.target / 3,
            p.tech,
            p.repairs / 5,
            *(
                max(0, p.cooldowns[key] - game.tick) / 40
                for key in ("signal", "missile", "jam", "repair")
            ),
            (p.eliminated_tick or 0) / 360,
            float(p.eliminated_tick is not None),
            game.headquarters(p.index).hp / 500,
        )
    cx, cy = game.cfg["map"]["hq_local"]
    radius = game.cfg["map"].get("wall_radius", 2)
    wall_positions = [
        (cx + dx, cy + dy)
        for dx in range(-radius, radius + 1)
        for dy in range(-radius, radius + 1)
        if max(abs(dx), abs(dy)) == radius
    ]
    if modern:
        interior = [
            (cx, cy),
            *(tuple(pos) for _, pos in game.cfg["map"]["initial_buildings"]),
        ]
        for sites in game.cfg["map"]["building_sites"].values():
            for pos in sites:
                if tuple(pos) not in interior:
                    interior.append(tuple(pos))
        structure_positions = [*interior, *wall_positions]
    else:
        structure_positions = [(2, 2), (3, 3), (3, 1), (1, 3), (1, 1), *wall_positions]
    types = (
        ("hq", "cannon", "jammer", "wall", "mortar", "antiair")
        if modern
        else ("hq", "cannon", "jammer", "wall")
    )
    for e in game.entities:
        if e.type in UNIT_TYPES:
            u = game.cfg["units"][e.type]
            goal = e.objective or (0, 0)
            command = e.command_goal or (0, 0)
            arrays["units"][e.player, e.slot] = (
                1,
                UNIT_TYPES.index(e.type) / 3,
                e.hp / e.max_hp,
                e.x / scale,
                e.y / scale,
                e.birth / 360,
                max(0, u["attack_ticks"] - (game.tick - e.last_attack))
                / u["attack_ticks"],
                max(0, u["move_ticks"] - (game.tick - e.last_move)) / u["move_ticks"],
                goal[0] / scale,
                goal[1] / scale,
                float(e.objective is not None),
                float(e.uid in game.connected),
                float(game.jammed(e.pos, e.player)),
                e.uid / 10000,
                1 if e.type == "drone" else 0,
                e.command_uid / 10000,
                command[0] / scale,
                command[1] / scale,
                max(0, e.command_until - game.tick) / 24,
                float(e.command_goal is not None),
            )
        else:
            slot = structure_positions.index(game.local(e.pos, e.player))
            interval = (
                game.cfg["buildings"][e.type].get("attack_ticks", 2) if modern else 2
            )
            arrays["structures"][e.player, slot] = (
                1,
                types.index(e.type) / (len(types) - 1),
                e.hp / e.max_hp,
                e.x / scale,
                e.y / scale,
                float(e.gate),
                max(0, interval - (game.tick - e.last_attack)) / interval,
                e.birth / 360,
                e.uid / 10000,
                float(game.players[e.player].alive),
            )
    for n in game.nodes:
        arrays["nodes"][n["index"]] = (
            n["x"] / scale,
            n["y"] / scale,
            n["owner"] / 3,
            n["progress"] / game.cfg["nodes"]["capture_ticks"],
            n["progress_player"] / 3,
            float(n["index"] in game.connected_relays[player]),
            float(game.jammed((n["x"], n["y"]), player)),
        )
    for b in game.beacons:
        arrays["signals"][b["player"]] = (
            1,
            b["center"][0] / scale,
            b["center"][1] / scale,
            max(0, b["until"] - game.tick) / game.cfg["signal"]["duration"],
            float(game.beacon_active(b)),
            b["uid"] / 10000,
        )
    for c in game.clouds:
        arrays["clouds"][c["player"]] = (
            1,
            c["center"][0] / scale,
            c["center"][1] / scale,
            max(0, c["until"] - game.tick) / game.cfg["jam"]["duration"],
            c["uid"] / 10000,
            1,
        )
    for m in game.projectiles:
        slot = 0 if m["type"] == "missile" else 1
        arrays["projectiles"][m["player"], slot] = (
            1,
            m["origin"][0] / scale,
            m["origin"][1] / scale,
            m["center"][0] / scale,
            m["center"][1] / scale,
            (m["land_tick"] - game.tick) / 8,
            float(m["locked"]),
            (m["beacon_uid"] or 0) / 10000,
            m["uid"] / 10000,
        )
    return arrays


class FourWayEnv:
    metadata: ClassVar[dict] = {
        "name": "THUAI10-Disconnect-v0.5",
        "obs_schema_version": SCHEMA,
    }

    def __init__(self, seed=0, config=None):
        self.game = FourWayGame(seed, config)
        self.agents = list(SIDES)

    def reset(self, seed=None):
        self.game.reset(seed)
        self.agents = list(SIDES)
        return {
            side: observe(self.game, i) for i, side in enumerate(SIDES)
        }, self.info()

    def info(self):
        return {
            "mask": self.game.legal_masks(),
            "alive": {side: p.alive for side, p in zip(SIDES, self.game.players)},
            "schema": self.game.cfg["obs_schema_version"],
        }

    def step(self, actions):
        out = self.game.step(actions)
        obs = {side: observe(self.game, i) for i, side in enumerate(SIDES)}
        rewards = {side: 0.0 for side in SIDES}
        terminal = {
            side: self.game.over or not p.alive
            for side, p in zip(SIDES, self.game.players)
        }
        for event in out["events"]:
            if event["type"] == "eliminated":
                rewards[SIDES[event["player"]]] = -1.0
        if self.game.over and self.game.winner >= 0:
            rewards[SIDES[self.game.winner]] = 1.0
        self.agents = [
            side
            for side, p in zip(SIDES, self.game.players)
            if p.alive and not self.game.over
        ]
        info = self.info()
        info["events"], info["diagnostics"] = out["events"], out["illegal"]
        return obs, rewards, terminal, {side: False for side in SIDES}, info
