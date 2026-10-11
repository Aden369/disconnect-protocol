"""通信网络、可摧毁城墙、信标制导和四方同步淘汰。"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs/balance-v0.5.json"
SIDES = ("p0", "p1", "p2", "p3")
UNIT_TYPES = ("dog", "robot", "siege", "drone")
N_ACTIONS = 41


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def rotate(pos, owner, size=21):
    x, y = pos
    for _ in range(owner % 4):
        x, y = size - 1 - y, x
    return x, y


def line_cells(a, b):
    """Bresenham 格线，不含起点和终点。"""
    x, y = a
    bx, by = b
    dx, dy = abs(bx - x), -abs(by - y)
    sx, sy = (1 if x < bx else -1), (1 if y < by else -1)
    error = dx + dy
    cells = []
    while (x, y) != (bx, by):
        twice = 2 * error
        if twice >= dy:
            error += dy
            x += sx
        if twice <= dx:
            error += dx
            y += sy
        if (x, y) != (bx, by):
            cells.append((x, y))
    return cells


@dataclass
class Entity:
    uid: int
    player: int
    type: str
    x: int
    y: int
    hp: int
    max_hp: int
    slot: int = -1
    gate: bool = False
    birth: int = 0
    last_attack: int = -10000
    last_move: int = -10000
    objective: tuple[int, int] | None = None
    command_uid: int = -1
    command_goal: tuple[int, int] | None = None
    command_until: int = 0

    @property
    def pos(self):
        return self.x, self.y


@dataclass
class Company:
    index: int
    resources: int
    target: int
    tech: int = 0
    eliminated_tick: int | None = None
    repairs: int = 0
    cooldowns: dict = field(
        default_factory=lambda: {"signal": 0, "missile": 0, "jam": 0, "repair": 0}
    )

    @property
    def alive(self):
        return self.eliminated_tick is None


class FourWayGame:
    def __init__(self, seed=0, config=None):
        self.cfg = copy.deepcopy(
            config or json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        )
        self.seed = seed
        self.reset()

    def reset(self, seed=None):
        if seed is not None:
            self.seed = seed
        self.tick = 0
        self.steps = 0
        self.next_uid = 0
        self.entities = []
        self.players = [
            Company(i, self.cfg["economy"]["initial"], (i + 1) % 4) for i in range(4)
        ]
        self.nodes = [
            {
                "index": i,
                "x": p[0],
                "y": p[1],
                "owner": -1,
                "progress": 0,
                "progress_player": -1,
            }
            for i, p in enumerate(self.cfg["map"]["nodes"])
        ]
        self.beacons = []
        self.clouds = []
        self.projectiles = []
        self.connected = set()
        self.connected_relays = [set() for _ in range(4)]
        self.network_links = []
        self.activity = []
        self.frame_events = []
        self.winner = None
        self.over = False
        self.end_reason = None
        self.actions = []
        self.checks = []
        for p in self.players:
            center = tuple(self.cfg["map"]["hq_local"])
            radius = self.cfg["map"].get("wall_radius", 2)
            self.spawn(p.index, "hq", self.world(center, p.index))
            for kind, pos in self.cfg["map"].get(
                "initial_buildings", [("cannon", (3, 3))]
            ):
                self.spawn(p.index, kind, self.world(pos, p.index))
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) == radius:
                        self.spawn(
                            p.index,
                            "wall",
                            self.world((center[0] + dx, center[1] + dy), p.index),
                            gate=(dx, dy) in ((radius, 0), (0, radius)),
                        )
            for kind in ("dog", "dog", "robot", "drone"):
                self.produce_unit(p.index, kind)
        self.compute_network()
        return self.frame()

    def world(self, pos, player):
        return rotate(tuple(pos), player, self.cfg["map"]["size"])

    def local(self, pos, player):
        return rotate(tuple(pos), -player, self.cfg["map"]["size"])

    def spawn(self, player, kind, pos, **kwargs):
        spec = self.cfg["units"].get(kind, self.cfg["buildings"].get(kind))
        entity = Entity(
            self.next_uid,
            player,
            kind,
            *pos,
            spec["hp"],
            spec["hp"],
            birth=self.tick,
            **kwargs,
        )
        self.next_uid += 1
        self.entities.append(entity)
        return entity

    def headquarters(self, player):
        return next(e for e in self.entities if e.player == player and e.type == "hq")

    def units(self, player):
        return [
            e
            for e in self.entities
            if e.player == player and e.type in UNIT_TYPES and e.hp > 0
        ]

    def structures(self, player):
        return [
            e
            for e in self.entities
            if e.player == player and e.type not in UNIT_TYPES and e.hp > 0
        ]

    def produce_unit(self, player, kind):
        army = self.units(player)
        slot = next(
            i
            for i in range(self.cfg["limits"]["units"])
            if i not in {e.slot for e in army}
        )
        deploy = self.cfg["map"]["deploy_local"][slot % 2]
        entity = self.spawn(player, kind, self.world(deploy, player), slot=slot)
        if kind == "dog":
            candidates = [n for n in self.nodes if n["owner"] != player] or self.nodes
            # Give newly produced dogs different missions rather than piling every squad onto one relay.
            node = sorted(
                candidates,
                key=lambda n: (
                    distance(entity.pos, (n["x"], n["y"])),
                    (n["index"] - player) % 4,
                ),
            )[slot % min(2, len(candidates))]
            entity.objective = (node["x"], node["y"])
        else:
            entity.objective = (
                self.headquarters(self.players[player].target).pos
                if any(
                    e.type == "hq" and e.player == self.players[player].target
                    for e in self.entities
                )
                else (
                    self.world(self.cfg["map"]["hq_local"], self.players[player].target)
                    if "initial_buildings" in self.cfg["map"]
                    else self.world((18, 2), player)
                )
            )
        return entity

    def region(self, number):
        coords = self.cfg["map"]["regions"]
        return coords[number % 3], coords[number // 3]

    def jammed(self, pos, player):
        for c in self.clouds:
            if (
                c["player"] != player
                and distance(pos, c["center"]) <= self.cfg["jam"]["radius"]
            ):
                return True
        for e in self.entities:
            if (
                e.type == "jammer"
                and e.hp > 0
                and e.player != player
                and self.players[e.player].alive
                and distance(pos, e.pos) <= self.cfg["buildings"]["jammer"]["radius"]
            ):
                return True
        return False

    def compute_network(self):
        self.connected = set()
        self.connected_relays = [set() for _ in range(4)]
        self.network_links = []
        net = self.cfg["network"]
        for p in self.players:
            if not p.alive:
                continue
            hq = self.headquarters(p.index)
            if self.jammed(hq.pos, p.index):
                continue
            relay_set = self.connected_relays[p.index]
            available = [
                n
                for n in self.nodes
                if n["owner"] == p.index and not self.jammed((n["x"], n["y"]), p.index)
            ]
            changed = True
            while changed:
                changed = False
                for n in available:
                    pos = (n["x"], n["y"])
                    if n["index"] in relay_set:
                        continue
                    link = distance(hq.pos, pos) <= net["hq_link"] or any(
                        distance(pos, (other["x"], other["y"])) <= net["relay_link"]
                        for other in available
                        if other["index"] in relay_set
                    )
                    if link:
                        origin = (
                            hq.pos
                            if distance(hq.pos, pos) <= net["hq_link"]
                            else next(
                                (other["x"], other["y"])
                                for other in available
                                if other["index"] in relay_set
                                and distance(pos, (other["x"], other["y"]))
                                <= net["relay_link"]
                            )
                        )
                        self.network_links.append(
                            {"player": p.index, "from": origin, "to": pos}
                        )
                        relay_set.add(n["index"])
                        changed = True
            army = self.units(p.index)
            for e in army:
                if self.jammed(e.pos, p.index):
                    continue
                if distance(e.pos, hq.pos) <= net["hq_coverage"] or any(
                    distance(e.pos, (n["x"], n["y"])) <= net["relay_coverage"]
                    for n in available
                    if n["index"] in relay_set
                ):
                    self.connected.add(e.uid)
            changed = True
            while changed:
                changed = False
                drones = [
                    e for e in army if e.type == "drone" and e.uid in self.connected
                ]
                for e in army:
                    if (
                        e.uid not in self.connected
                        and not self.jammed(e.pos, p.index)
                        and any(
                            distance(e.pos, d.pos) <= net["drone_coverage"]
                            for d in drones
                        )
                    ):
                        self.connected.add(e.uid)
                        changed = True

    def beacon_active(self, beacon):
        return beacon["until"] > self.tick and not self.jammed(
            beacon["center"], beacon["player"]
        )

    def mask(self, player):
        mask = [False] * N_ACTIONS
        mask[0] = True
        p = self.players[player]
        if self.over or not p.alive:
            return mask
        for i, kind in enumerate(UNIT_TYPES):
            spec = self.cfg["units"][kind]
            within_type_limit = kind != "drone" or sum(
                e.type == "drone" for e in self.units(player)
            ) < self.cfg["limits"].get("drones", 12)
            mask[1 + i] = (
                within_type_limit
                and p.resources >= spec["cost"]
                and len(self.units(player)) + spec["batch"]
                <= self.cfg["limits"]["units"]
            )
        for aid, kind, limit in ((5, "cannon", "cannons"), (6, "jammer", "jammers")):
            mask[aid] = (
                p.resources >= self.cfg["buildings"][kind]["cost"]
                and sum(e.type == kind for e in self.structures(player))
                < self.cfg["limits"][limit]
            )
        support = self.cfg["support"]
        mask[7] = p.resources >= support["wall_cost"] and any(
            e.type == "wall" and e.hp < e.max_hp for e in self.structures(player)
        )
        hq = self.headquarters(player)
        mask[8] = (
            p.resources >= support["repair_cost"]
            and p.repairs < self.cfg["limits"]["repairs"]
            and self.tick >= p.cooldowns["repair"]
            and hq.hp < hq.max_hp
        )
        mask[9] = p.tech == 0 and p.resources >= support["tech_cost"]
        for target in range(4):
            mask[10 + target] = target != player and self.players[target].alive
        linked = any(e.uid in self.connected for e in self.units(player))
        for r in range(9):
            mask[14 + r] = (
                linked
                and p.resources >= self.cfg["signal"]["cost"]
                and self.tick >= p.cooldowns["signal"]
            )
            mask[23 + r] = (
                p.resources >= self.cfg["missile"]["cost"]
                and self.tick >= p.cooldowns["missile"]
                and self.tick + self.cfg["missile"]["flight"]
                <= self.cfg["time"]["max_ticks"]
                and any(
                    b["player"] == player
                    and b["center"] == self.region(r)
                    and self.beacon_active(b)
                    for b in self.beacons
                )
            )
            mask[32 + r] = (
                p.resources >= self.cfg["jam"]["cost"]
                and self.tick >= p.cooldowns["jam"]
            )
        return mask

    def legal_masks(self):
        return {side: self.mask(i) for i, side in enumerate(SIDES)}

    def execute(self, player, action):
        p = self.players[player]
        events = []

        def event(kind, **fields):
            events.append({"type": kind, "player": player, "tick": self.tick, **fields})

        if 1 <= action <= 4:
            kind = UNIT_TYPES[action - 1]
            spec = self.cfg["units"][kind]
            p.resources -= spec["cost"]
            for _ in range(spec["batch"]):
                self.produce_unit(player, kind)
            event("deploy", unit=kind, count=spec["batch"])
        elif action in (5, 6):
            kind = "cannon" if action == 5 else "jammer"
            sites = (
                self.cfg["map"]
                .get("building_sites", {})
                .get(kind, ((3, 1), (1, 3)) if kind == "cannon" else ((1, 1),))
            )
            occupied = {e.pos for e in self.structures(player)}
            pos = next(
                self.world(site, player)
                for site in sites
                if self.world(site, player) not in occupied
            )
            p.resources -= self.cfg["buildings"][kind]["cost"]
            self.spawn(player, kind, pos)
            event("build", building=kind, pos=pos)
        elif action == 7:
            p.resources -= self.cfg["support"]["wall_cost"]
            for e in self.structures(player):
                if e.type == "wall":
                    e.hp = min(e.max_hp, e.hp + self.cfg["support"]["wall_repair"])
            event("wall_repair")
        elif action == 8:
            p.resources -= self.cfg["support"]["repair_cost"]
            hq = self.headquarters(player)
            healed = min(hq.max_hp - hq.hp, self.cfg["support"]["repair_hp"])
            hq.hp += healed
            p.repairs += 1
            p.cooldowns["repair"] = self.tick + self.cfg["support"]["repair_cooldown"]
            event("repair", healed=healed)
        elif action == 9:
            p.resources -= self.cfg["support"]["tech_cost"]
            p.tech = 1
            event("tech")
        elif 10 <= action <= 13:
            p.target = action - 10
            for e in self.units(player):
                if e.type != "dog" and e.uid in self.connected:
                    e.objective = self.headquarters(p.target).pos
            event("target", target=p.target)
        elif 14 <= action <= 22:
            p.resources -= self.cfg["signal"]["cost"]
            p.cooldowns["signal"] = self.tick + self.cfg["signal"]["cooldown"]
            self.beacons = [b for b in self.beacons if b["player"] != player]
            b = {
                "uid": self.next_uid,
                "player": player,
                "center": self.region(action - 14),
                "until": self.tick + self.cfg["signal"]["duration"],
            }
            self.next_uid += 1
            self.beacons.append(b)
            event("signal", center=b["center"])
        elif 23 <= action <= 40:
            missile = action <= 31
            kind = "missile" if missile else "jam"
            center = self.region(action - (23 if missile else 32))
            p.resources -= self.cfg[kind]["cost"]
            p.cooldowns[kind] = self.tick + self.cfg[kind]["cooldown"]
            beacon = next(
                (
                    b
                    for b in self.beacons
                    if b["player"] == player and b["center"] == center
                ),
                None,
            )
            projectile = {
                "uid": self.next_uid,
                "player": player,
                "type": kind,
                "origin": self.headquarters(player).pos,
                "center": center,
                "start": self.tick,
                "land_tick": self.tick + self.cfg[kind]["flight"],
                "locked": True,
                "beacon_uid": beacon["uid"] if beacon else None,
            }
            self.next_uid += 1
            self.projectiles.append(projectile)
            event("missile_launch" if missile else "jam_launch", center=center)
        return events

    def movement_goal(self, unit):
        if unit.type == "drone" and not self.cfg["units"]["drone"].get("armed", True):
            if self.jammed(unit.pos, unit.player):
                return self.headquarters(unit.player).pos, "受屏蔽，返回总部"
            if unit.command_until > self.tick:
                return unit.command_goal, "通信部署：执行信号指令"
            ground = [e for e in self.units(unit.player) if e.type != "drone"]
            # Prefer the siege front; two drones support different ground units.
            ground.sort(key=lambda e: (e.type != "siege", e.type != "robot", e.slot))
            if ground:
                drones = sorted(
                    (e for e in self.units(unit.player) if e.type == "drone"),
                    key=lambda e: e.slot,
                )
                escort = ground[drones.index(unit) % len(ground)]
                return escort.pos, "通信接力：跟随" + escort.type
            return self.headquarters(unit.player).pos, "无地面部队，返回总部"
        if unit.command_until > self.tick:
            return (
                unit.command_goal,
                "执行信号指令" if unit.uid in self.connected else "离线继续已收指令",
            )
        # A destroyed objective HQ must not leave units staring at a wreck forever.
        if unit.type != "dog" and unit.objective is not None:
            old = next(
                (
                    p
                    for p in self.players
                    if self.headquarters(p.index).pos == unit.objective
                ),
                None,
            )
            if old and not old.alive:
                live = [p for p in self.players if p.alive and p.index != unit.player]
                if live:
                    unit.objective = self.headquarters(
                        min(
                            live,
                            key=lambda p: (
                                distance(unit.pos, self.headquarters(p.index).pos),
                                (p.index - unit.player) % 4,
                            ),
                        ).index
                    ).pos
        return (
            unit.objective or unit.pos,
            "驻守中继" if unit.type == "dog" else "突破敌方基地",
        )

    def receive_commands(self):
        for unit in self.entities:
            if unit.type not in UNIT_TYPES or unit.hp <= 0:
                continue
            if unit.command_until > self.tick and (
                self.jammed(unit.pos, unit.player)
                or self.jammed(unit.command_goal, unit.player)
            ):
                unit.command_until = 0
            beacon = next(
                (
                    b
                    for b in self.beacons
                    if b["player"] == unit.player and self.beacon_active(b)
                ),
                None,
            )
            if (
                beacon
                and unit.uid in self.connected
                and unit.command_uid != beacon["uid"]
            ):
                unit.command_uid = beacon["uid"]
                unit.command_goal = beacon["center"]
                unit.command_until = beacon["until"]

    def next_step(self, unit, goal, cache):
        key = (unit.player, unit.type == "drone", unit.pos, goal)
        if key in cache:
            return cache[key]
        air = unit.type == "drone"
        blocked = {
            e.pos
            for e in self.entities
            if e.hp > 0
            and e.type not in UNIT_TYPES
            and self.players[e.player].alive
            and not (air and e.type == "wall")
            and not (e.type == "wall" and e.gate and e.player == unit.player)
        }
        start = unit.pos
        directions = []
        for d in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            # Rotate vectors, not positions.
            dx, dy = d
            for _ in range(unit.player):
                dx, dy = -dy, dx
            directions.append((dx, dy))
        reached = {start: (0, None)}
        queue = deque([start])
        size = self.cfg["map"]["size"]
        while queue:
            pos = queue.popleft()
            length, first = reached[pos]
            for dx, dy in directions:
                nxt = (pos[0] + dx, pos[1] + dy)
                if (
                    nxt in reached
                    or nxt in blocked
                    or not (0 <= nxt[0] < size and 0 <= nxt[1] < size)
                ):
                    continue
                reached[nxt] = (length + 1, nxt if first is None else first)
                queue.append(nxt)
        endpoint = min(
            reached,
            key=lambda p: (
                distance(p, goal),
                reached[p][0],
                self.local(p, unit.player)[1],
                self.local(p, unit.player)[0],
            ),
        )
        result = reached[endpoint][1]
        cache[key] = result
        return result

    def shot_clear(self, attacker, target):
        if attacker.type == "drone":
            return True
        blocking = {
            e.pos
            for e in self.entities
            if e.type == "wall"
            and e.hp > 0
            and e.player != attacker.player
            and self.players[e.player].alive
        }
        return not any(
            cell in blocking for cell in line_cells(attacker.pos, target.pos)
        )

    def resolve_tick(self):
        self.tick += 1
        events = []
        self.activity = []
        self.clouds = [c for c in self.clouds if c["until"] > self.tick]
        self.beacons = [b for b in self.beacons if b["until"] > self.tick]
        for projectile in self.projectiles:
            if projectile["type"] == "jam" and projectile["land_tick"] == self.tick:
                self.clouds.append(
                    {
                        "uid": projectile["uid"],
                        "player": projectile["player"],
                        "center": projectile["center"],
                        "until": self.tick + self.cfg["jam"]["duration"],
                    }
                )
                events.append(
                    {
                        "type": "jam_cloud",
                        "player": projectile["player"],
                        "center": projectile["center"],
                        "tick": self.tick,
                    }
                )
        self.compute_network()
        self.receive_commands()
        for projectile in self.projectiles:
            if projectile["type"] == "missile" and projectile["locked"]:
                beacon = next(
                    (b for b in self.beacons if b["uid"] == projectile["beacon_uid"]),
                    None,
                )
                if beacon is None or not self.beacon_active(beacon):
                    projectile["locked"] = False
                    events.append(
                        {
                            "type": "lock_lost",
                            "player": projectile["player"],
                            "center": projectile["center"],
                            "tick": self.tick,
                        }
                    )
        attacks = []
        moves = []
        cache = {}
        for e in sorted(self.entities, key=lambda e: e.uid):
            if (
                e.hp <= 0
                or not self.players[e.player].alive
                or e.type not in (*UNIT_TYPES, "cannon", "mortar", "antiair")
            ):
                continue
            spec = self.cfg["units"].get(e.type, self.cfg["buildings"].get(e.type))
            enemies = [
                v
                for v in self.entities
                if v.hp > 0
                and v.player != e.player
                and self.players[v.player].alive
                and distance(e.pos, v.pos) <= spec["range"]
                and (e.type in UNIT_TYPES or v.type in UNIT_TYPES)
                and (not spec.get("air_only", False) or v.type == "drone")
                and spec.get("armed", True)
                and (v.type != "drone" or spec.get("anti_air", True))
                and (
                    (
                        v.type == "drone"
                        and self.cfg["rules_version"] != "game-rules-v0.3"
                    )
                    or spec.get("indirect", False)
                    or self.shot_clear(e, v)
                )
            ]
            intent = {
                "uid": e.uid,
                "player": e.player,
                "from": e.pos,
                "kind": "wait",
                "linked": e.uid in self.connected,
            }
            if enemies:
                target = min(
                    enemies,
                    key=lambda v: (
                        0
                        if (
                            (v.type not in UNIT_TYPES)
                            if e.type == "siege"
                            else (v.type in UNIT_TYPES)
                        )
                        else 1,
                        distance(e.pos, v.pos),
                        (v.player - e.player) % 4,
                        v.birth,
                        v.uid,
                    ),
                )
                intent.update(
                    target=target.pos,
                    target_uid=target.uid,
                    label="破坏城墙" if target.type == "wall" else "攻击" + target.type,
                )
                if self.tick - e.last_attack >= spec["attack_ticks"]:
                    e.last_attack = self.tick
                    dmg = (
                        spec["damage"]
                        if target.type in UNIT_TYPES
                        or e.type in ("cannon", "mortar", "antiair")
                        else spec["building_damage"]
                    )
                    dmg += (
                        self.players[e.player].tech
                        * self.cfg["support"][
                            "tech_cannon_damage"
                            if e.type in ("cannon", "mortar", "antiair")
                            else "tech_unit_damage"
                        ]
                        if target.type in UNIT_TYPES
                        or e.type in ("cannon", "mortar", "antiair")
                        else 0
                    )
                    if spec.get("splash", 0):
                        attacks.extend(
                            (v.uid, dmg)
                            for v in self.entities
                            if v.hp > 0
                            and v.player != e.player
                            and self.players[v.player].alive
                            and v.type in UNIT_TYPES
                            and v.type != "drone"
                            and distance(v.pos, target.pos) <= spec["splash"]
                        )
                    else:
                        attacks.append((target.uid, dmg))
                    intent.update(kind="attack", damage=dmg)
                else:
                    intent["label"] = "装填 / 等待攻击"
            elif e.type in UNIT_TYPES:
                goal, label = self.movement_goal(e)
                intent.update(target=goal, label=label)
                if self.tick - e.last_move >= spec["move_ticks"]:
                    nxt = self.next_step(e, goal, cache)
                    if nxt:
                        e.last_move = self.tick
                        moves.append((e, nxt))
                        intent.update(kind="move", next=nxt)
                    else:
                        intent["label"] = "驻守中继" if e.type == "dog" else "等待突破"
                else:
                    intent["label"] = "移动冷却"
            else:
                intent["label"] = "炮塔警戒"
            self.activity.append(intent)
        for e, pos in moves:
            e.x, e.y = pos
        damage = defaultdict(int)
        for uid, amount in attacks:
            damage[uid] += amount
        for projectile in self.projectiles:
            if projectile["type"] == "missile" and projectile["land_tick"] == self.tick:
                amount = self.cfg["missile"][
                    "damage" if projectile["locked"] else "lost_damage"
                ]
                hit = []
                for e in self.entities:
                    if (
                        e.hp > 0
                        and e.player != projectile["player"]
                        and self.players[e.player].alive
                        and distance(e.pos, projectile["center"])
                        <= self.cfg["missile"]["radius"]
                    ):
                        damage[e.uid] += amount
                        hit.append(e.uid)
                events.append(
                    {
                        "type": "missile_impact",
                        "player": projectile["player"],
                        "center": projectile["center"],
                        "damage": amount,
                        "locked": projectile["locked"],
                        "hit": hit,
                        "tick": self.tick,
                    }
                )
        self.projectiles = [p for p in self.projectiles if p["land_tick"] > self.tick]
        timing = self.cfg["time"]
        if (
            self.tick >= timing["overload_tick"]
            and self.tick % timing["decision_ticks"] == 0
        ):
            amount = timing["overload_initial"] + timing["overload_increment"] * (
                (self.tick - timing["overload_tick"]) // timing["overload_period"]
            )
            for p in self.players:
                if p.alive:
                    damage[self.headquarters(p.index).uid] += amount
            events.append({"type": "overload", "damage": amount, "tick": self.tick})
        for e in self.entities:
            if damage[e.uid]:
                e.hp = max(0, e.hp - damage[e.uid])
            if e.hp == 0 and e.type != "hq":
                events.append(
                    {
                        "type": "wall_destroyed"
                        if e.type == "wall"
                        else "entity_destroyed",
                        "player": e.player,
                        "entity": e.type,
                        "pos": e.pos,
                        "tick": self.tick,
                    }
                )
        self.entities = [e for e in self.entities if e.hp > 0 or e.type == "hq"]
        for p in self.players:
            if p.alive and self.headquarters(p.index).hp <= 0:
                p.eliminated_tick = self.tick
                self.entities = [
                    e for e in self.entities if e.player != p.index or e.type == "hq"
                ]
                self.beacons = [b for b in self.beacons if b["player"] != p.index]
                for n in self.nodes:
                    if n["owner"] == p.index:
                        n["owner"] = -1
                events.append(
                    {"type": "eliminated", "player": p.index, "tick": self.tick}
                )
        for n in self.nodes:
            present = {
                e.player
                for e in self.entities
                if e.type in UNIT_TYPES
                and e.hp > 0
                and self.cfg["units"][e.type].get("capture", True)
                and distance(e.pos, (n["x"], n["y"])) <= self.cfg["nodes"]["range"]
            }
            claimant = next(iter(present)) if len(present) == 1 else -1
            if claimant < 0 or n["owner"] == claimant:
                n["progress"], n["progress_player"] = 0, -1
            else:
                n["progress"] = (
                    n["progress"] + 1 if n["progress_player"] == claimant else 1
                )
                n["progress_player"] = claimant
                if n["progress"] >= self.cfg["nodes"]["capture_ticks"]:
                    n["owner"] = claimant
                    n["progress"], n["progress_player"] = 0, -1
                    events.append(
                        {
                            "type": "node_flip",
                            "player": claimant,
                            "node": n["index"],
                            "tick": self.tick,
                        }
                    )
        if self.tick % timing["decision_ticks"] == 0:
            for p in self.players:
                if p.alive:
                    p.resources = min(
                        self.cfg["economy"]["cap"],
                        p.resources
                        + self.cfg["economy"]["income"]
                        + self.cfg["economy"]["relay_income"]
                        * sum(n["owner"] == p.index for n in self.nodes),
                    )
        self.compute_network()
        living = [p.index for p in self.players if p.alive]
        if not living:
            self.finish(-1, "mutual_destruction", events)
        elif len(living) == 1 and not any(
            p["type"] == "missile" and p["player"] != living[0]
            for p in self.projectiles
        ):
            self.finish(living[0], "last_survivor", events)
        elif self.tick >= timing["max_ticks"]:
            self.finish(-1, "time_limit_draw", events)
        self.frame_events = events
        return events

    def finish(self, winner, reason, events):
        self.over = True
        self.winner = winner
        self.end_reason = reason
        events.append(
            {"type": "victory", "winner": winner, "reason": reason, "tick": self.tick}
        )

    def step(self, actions):
        if self.over:
            raise RuntimeError("对局已结束")
        self.compute_network()
        old_masks = self.legal_masks()
        values = [
            actions.get(side, 0) if isinstance(actions, dict) else actions[i]
            for i, side in enumerate(SIDES)
        ]
        effective = []
        illegal = []
        for i, value in enumerate(values):
            valid = (
                isinstance(value, int)
                and 0 <= value < N_ACTIONS
                and old_masks[SIDES[i]][value]
            )
            effective.append(value if valid else 0)
            if not valid:
                illegal.append(
                    {"player": i, "action": value, "reason": "illegal_as_wait"}
                )
        events = []
        for i, value in enumerate(effective):
            events.extend(self.execute(i, value))
        frames = []
        for _ in range(self.cfg["time"]["decision_ticks"]):
            events.extend(self.resolve_tick())
            frames.append(self.frame())
            if self.over:
                break
        self.steps += 1
        self.actions.append(effective)
        self.checks.append(self.checksum())
        return {
            "frames": frames,
            "events": events,
            "state": self.snapshot(),
            "done": self.over,
            "masks": self.legal_masks(),
            "illegal": illegal,
        }

    def snapshot(self):
        return {
            "rules_version": self.cfg["rules_version"],
            "tick": self.tick,
            "steps": self.steps,
            "next_uid": self.next_uid,
            "seed": self.seed,
            "players": [asdict(p) for p in self.players],
            "entities": [asdict(e) for e in self.entities],
            "nodes": copy.deepcopy(self.nodes),
            "beacons": copy.deepcopy(self.beacons),
            "clouds": copy.deepcopy(self.clouds),
            "projectiles": copy.deepcopy(self.projectiles),
            "winner": self.winner,
            "done": self.over,
            "end_reason": self.end_reason,
        }

    def frame(self):
        players = []
        for p in self.players:
            players.append(
                {
                    **asdict(p),
                    "alive": p.alive,
                    "hq": asdict(self.headquarters(p.index)),
                    "unit_count": len(self.units(p.index)),
                    "linked_count": sum(
                        e.uid in self.connected for e in self.units(p.index)
                    ),
                    "relay_count": sum(n["owner"] == p.index for n in self.nodes),
                }
            )
        beacons = [
            {**copy.deepcopy(b), "active": self.beacon_active(b)} for b in self.beacons
        ]
        return {
            "tick": self.tick,
            "phase": "overload"
            if self.tick >= self.cfg["time"]["overload_tick"]
            else "battle",
            "players": players,
            "units": [
                {
                    **asdict(e),
                    "linked": e.uid in self.connected,
                    "jammed": self.jammed(e.pos, e.player),
                }
                for e in self.entities
                if e.type in UNIT_TYPES
            ],
            "buildings": [
                asdict(e) for e in self.entities if e.type not in (*UNIT_TYPES, "wall")
            ],
            "walls": [asdict(e) for e in self.entities if e.type == "wall"],
            "nodes": copy.deepcopy(self.nodes),
            "signals": beacons,
            "clouds": copy.deepcopy(self.clouds),
            "projectiles": copy.deepcopy(self.projectiles),
            "activity": copy.deepcopy(self.activity),
            "network_links": copy.deepcopy(self.network_links),
            "events": copy.deepcopy(self.frame_events),
            "winner": self.winner,
            "done": self.over,
            "end_reason": self.end_reason,
        }

    def checksum(self):
        return hashlib.sha256(
            json.dumps(
                self.snapshot(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()

    def replay(self, meta=None):
        return {
            "schema_version": self.cfg["schema_version"],
            "rules_version": self.cfg["rules_version"],
            "config": copy.deepcopy(self.cfg),
            "seed": self.seed,
            "actions": copy.deepcopy(self.actions),
            "checks": list(self.checks),
            "final": {
                "winner": self.winner,
                "reason": self.end_reason,
                "tick": self.tick,
            },
            "meta": meta or {},
        }


def verify_replay(replay):
    game = FourWayGame(replay.get("seed", 0), replay["config"])
    for i, actions in enumerate(replay["actions"]):
        game.step(actions)
        if game.checks[-1] != replay["checks"][i]:
            return {"ok": False, "failed_step": i}
    return {
        "ok": game.winner == replay["final"]["winner"]
        and game.end_reason == replay["final"]["reason"]
        and game.tick == replay["final"]["tick"],
        "steps": game.steps,
        "winner": game.winner,
    }
