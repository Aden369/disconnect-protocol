"""四种可解释基线：破城、导弹、电子战和堡垒。每决策各调用一次。"""

import random

from .game import distance

POLICIES = {
    "breach": "破墙突击",
    "missile": "信标制导",
    "electronic": "电子战压制",
    "fortress": "堡垒反击",
}


def ground_region(game, player, radius, linked_only=False):
    """Pick an existing nine-zone aim point with at least two relevant ground targets."""
    army = [
        e
        for e in game.entities
        if e.type in ("dog", "robot", "siege")
        and e.hp > 0
        and e.player != player
        and game.players[e.player].alive
    ]
    friends = game.units(player)
    candidates = []
    for r in range(9):
        center = game.region(r)
        if game.jammed(center, player) and not linked_only:
            continue
        victims = [
            e
            for e in army
            if distance(e.pos, center) <= radius
            and (
                not linked_only
                or (
                    e.uid in game.connected
                    and not game.jammed(e.pos, e.player)
                    and any(distance(e.pos, f.pos) <= 6 for f in friends)
                )
            )
        ]
        value = sum(min(e.hp, game.cfg["missile"]["damage"]) for e in victims)
        if len(victims) >= 2 and (linked_only or value >= 90):
            candidates.append((len(victims), value, game.local(center, player), r))
    if not candidates:
        return None
    return min(candidates, key=lambda c: (-c[0], -c[1], c[2][1], c[2][0]))[3]


class Policy:
    def __init__(self, name, seed=0):
        if name not in POLICIES:
            raise ValueError("未知四方策略")
        self.name = name
        self.rng = random.Random(seed)
        self.last_reason = ""

    def act(self, game, player):
        self.last_reason = ""
        mask = game.mask(player)
        p = game.players[player]
        if not p.alive:
            return 0
        hq = game.headquarters(player)
        region_coords = game.cfg["map"]["regions"]

        def region(pos):
            return region_coords.index(pos[1]) * 3 + region_coords.index(pos[0])

        home_region = region(hq.pos)
        # A visible incoming guided strike warrants a timed EMP response, not a resource score.
        incoming = [
            m
            for m in game.projectiles
            if m["type"] == "missile"
            and m["player"] != player
            and distance(m["center"], hq.pos) <= 2
            and m["locked"]
        ]
        if incoming and mask[32 + home_region]:
            return 32 + home_region
        if hq.hp < 230 and mask[8]:
            return 8
        if self.name == "electronic":
            guided = sorted(
                [
                    m
                    for m in game.projectiles
                    if m["type"] == "missile" and m["player"] != player and m["locked"]
                ],
                key=lambda m: (m["land_tick"], (m["player"] - player) % 4),
            )
            for missile in guided:
                aid = 32 + region(missile["center"])
                if mask[aid]:
                    return aid
        own_missile = any(
            m["type"] == "missile" and m["player"] == player for m in game.projectiles
        )
        if self.name == "electronic":
            front = ground_region(
                game, player, game.cfg["jam"]["radius"], linked_only=True
            )
            if front is not None and mask[32 + front]:
                self.last_reason = "EMP覆盖前线联网地面部队，取消已收信号指令"
                return 32 + front
        ground = ground_region(game, player, game.cfg["missile"]["radius"])
        if ground is not None:
            if mask[23 + ground]:
                self.last_reason = "导弹打击地面集群；落地时重新判断命中"
                return 23 + ground
            if (
                not own_missile
                and mask[14 + ground]
                and game.tick >= p.cooldowns["missile"]
                and p.resources
                >= game.cfg["signal"]["cost"] + game.cfg["missile"]["cost"]
            ):
                self.last_reason = "给地面集群建立导弹信标"
                return 14 + ground
        live = [
            other.index
            for other in game.players
            if other.alive and other.index != player
        ]
        if not live:
            return 0
        threats = [
            u
            for u in game.entities
            if u.type in game.cfg["units"]
            and u.player != player
            and game.players[u.player].alive
            and distance(u.pos, hq.pos) <= 6
        ]
        target = (
            p.target if p.target in live else min(live, key=lambda i: (i - player) % 4)
        )
        if threats:
            target = min(
                threats,
                key=lambda e: (
                    distance(e.pos, hq.pos),
                    (e.player - player) % 4,
                    e.birth,
                    e.uid,
                ),
            ).player
        elif self.name == "missile" and game.jammed(
            game.headquarters(target).pos, player
        ):
            unjammed = [
                i for i in live if not game.jammed(game.headquarters(i).pos, player)
            ]
            if unjammed:
                target = min(unjammed, key=lambda i: (i - player) % 4)
        if target != p.target and mask[10 + target]:
            return 10 + target
        target_region = region(game.headquarters(target).pos)
        beacon = next(
            (
                b
                for b in game.beacons
                if b["player"] == player
                and b["center"] == game.region(target_region)
                and game.beacon_active(b)
            ),
            None,
        )
        if mask[23 + target_region]:
            return 23 + target_region
        if self.name == "electronic":
            if mask[6]:
                return 6
            # Mask the targeted rival's command source even before a missile is airborne.
            if mask[32 + target_region]:
                return 32 + target_region
        if self.name == "fortress" and mask[5]:
            return 5
        if (
            self.name == "missile"
            and not beacon
            and not own_missile
            and p.resources >= game.cfg["signal"]["cost"] + game.cfg["missile"]["cost"]
            and mask[14 + target_region]
        ):
            return 14 + target_region
        if self.name == "missile":
            # Save a real missile budget instead of buying every affordable unit forever.
            if len(game.units(player)) < 3 and p.resources >= 85 and mask[4]:
                return 4
            return 0
        army = game.units(player)
        preferred = {
            "breach": [3, 2, 4, 1],
            "missile": [2, 4, 3, 1],
            "electronic": [2, 3, 1, 4],
            "fortress": [2, 3, 1, 4],
        }[self.name]
        if len(army) < 8:
            for action in preferred:
                if mask[action]:
                    return action
        if (
            not beacon
            and not own_missile
            and p.resources >= game.cfg["signal"]["cost"] + game.cfg["missile"]["cost"]
            and mask[14 + target_region]
        ):
            return 14 + target_region
        if self.name == "fortress" and mask[7] and p.resources > 60:
            return 7
        if mask[9] and len(army) >= 6:
            return 9
        if not any(u.type == "dog" for u in army) and mask[1]:
            return 1
        if len(army) < game.cfg["limits"]["units"]:
            for action in preferred:
                if mask[action]:
                    return action
        return 0


class RandomPolicy:
    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def act(self, game, player):
        return self.rng.choice([i for i, ok in enumerate(game.mask(player)) if ok])
