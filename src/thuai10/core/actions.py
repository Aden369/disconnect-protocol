"""动作空间：固定 Discrete(72) 字典、阶段掩码与结算执行。

动作编号含义永不静默改变（规则 v0.1 / game-rules.md §8）：
0 WAIT；1..18 建筑×槽位；19 科技；20..22 生产；23..37 槽位对；
38..44 维修；45..53 部署；54..62 信号；63..71 轰炸。
区域按玩家本地坐标 y=2,5,8 每行 x=2,8,14 排序，右方执行前映射到世界坐标。
非法或缺失动作一律按 WAIT 执行，不扣资源，不自动改选。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import BUILDING_TYPES, ROUTES, UNIT_TYPES, BalanceConfig
from .model import (
    PHASE_ATTACK,
    PHASE_BUILD,
    PHASE_LAYOUT,
    PHASE_REPAIR,
    BombState,
    Building,
    GameState,
    PlayerState,
    Unit,
)

ACTION_WAIT = 0
ACTION_TECH = 19
N_ACTIONS = 72

# 槽位对顺序：(0,1),(0,2)..(4,5)
SLOT_PAIRS: list[tuple[int, int]] = [
    (a, b) for a in range(6) for b in range(a + 1, 6)
]
assert len(SLOT_PAIRS) == 15


@dataclass(frozen=True)
class Action:
    aid: int
    kind: str                       # wait / build / tech / produce / layout / repair / deploy / signal / bomb
    btype: Optional[str] = None     # build
    slot: Optional[int] = None      # build / layout / repair
    slot_b: Optional[int] = None    # layout
    utype: Optional[str] = None     # produce / deploy
    route: Optional[int] = None     # deploy 0..2
    region: Optional[int] = None    # signal / bomb 0..8（本地排序）


def region_center_local(region: int, cfg: BalanceConfig) -> tuple[int, int]:
    xs = cfg.map_data["region_xs"]
    ys = cfg.map_data["region_ys"]
    return (xs[region % 3], ys[region // 3])


def decode(aid: Optional[int], cfg: BalanceConfig) -> Action:
    if aid is None or not (0 <= aid < N_ACTIONS):
        return Action(0, "wait")
    if aid == 0:
        return Action(0, "wait")
    if 1 <= aid <= 18:
        t = (aid - 1) // 6
        return Action(aid, "build", btype=BUILDING_TYPES[t], slot=(aid - 1) % 6)
    if aid == 19:
        return Action(19, "tech")
    if 20 <= aid <= 22:
        return Action(aid, "produce", utype=UNIT_TYPES[aid - 20])
    if 23 <= aid <= 37:
        a, b = SLOT_PAIRS[aid - 23]
        return Action(aid, "layout", slot=a, slot_b=b)
    if 38 <= aid <= 44:
        return Action(aid, "repair", slot=None if aid == 38 else aid - 39)
    if 45 <= aid <= 53:
        return Action(aid, "deploy", utype=UNIT_TYPES[(aid - 45) // 3], route=(aid - 45) % 3)
    if 54 <= aid <= 62:
        return Action(aid, "signal", region=aid - 54)
    return Action(aid, "bomb", region=aid - 63)


def legal_actions(state: GameState, player_idx: int, cfg: BalanceConfig) -> list[bool]:
    """当前决策点对 `player_idx` 的 72 维动作掩码。WAIT 恒合法。"""
    mask = [False] * N_ACTIONS
    mask[0] = True
    if state.over:
        return mask
    p = state.players[player_idx]
    phase = state.phase

    if phase == PHASE_BUILD:
        for t, btype in enumerate(BUILDING_TYPES):
            cost = cfg.buildings[btype]["cost"]
            max_of = cfg.limits[f"max_{btype}"]
            cur = sum(1 for b in p.slots if b is not None and b.btype == btype)
            for slot in range(6):
                ok = (
                    p.slots[slot] is None
                    and p.building_count() < cfg.limits["max_buildings"]
                    and cur < max_of
                    and p.resources >= cost
                )
                mask[1 + t * 6 + slot] = ok
        if (
            not p.tech_upgraded
            and p.tech < cfg.economy["tech_max_level"]
            and p.resources >= cfg.economy["tech_cost"]
        ):
            mask[19] = True
        B = p.barracks_count()
        if B > 0:
            for i, utype in enumerate(UNIT_TYPES):
                ucfg = cfg.units[utype]
                if ucfg["requires_tech"] > p.tech:
                    continue
                batch = cfg.batch_size(utype, B)
                cost = batch * ucfg["price"]
                if (
                    p.resources >= cost
                    and p.alive_unit_count() + batch <= cfg.limits["max_units"]
                ):
                    mask[20 + i] = True

    elif phase == PHASE_LAYOUT:
        if not p.layout_used:
            for i, (a, b) in enumerate(SLOT_PAIRS):
                mask[23 + i] = p.slots[a] is not None or p.slots[b] is not None

    elif phase == PHASE_REPAIR:
        if not p.repair_used and p.resources >= cfg.economy["repair_cost"]:
            targets = [p.hq] + list(p.slots)
            for i, b in enumerate(targets):
                if b is not None and 0 < b.hp < b.max_hp:
                    mask[38 + i] = True

    elif phase == PHASE_ATTACK:
        if p.deploy_used < cfg.limits["deploy_per_round"]:
            for i, utype in enumerate(UNIT_TYPES):
                if p.reserve_of(utype):
                    mask[45 + i * 3 : 48 + i * 3] = [True, True, True]
        if p.resources >= cfg.signal["cost"]:
            mask[54:63] = [True] * 9
        if not p.bomb_used and p.resources >= cfg.bomb["cost"]:
            mask[63:72] = [True] * 9
    return mask


def validate(
    aid: Optional[int], state: GameState, player_idx: int, cfg: BalanceConfig
) -> bool:
    if aid is None or not (0 <= aid < N_ACTIONS):
        return False
    return legal_actions(state, player_idx, cfg)[aid]


def execute(
    aid: Optional[int], state: GameState, player_idx: int, cfg: BalanceConfig
) -> list[dict]:
    """在决策边界执行动作；返回事件列表。非法动作按 WAIT。"""
    if not validate(aid, state, player_idx, cfg):
        aid = 0
    action = decode(aid, cfg)
    p = state.players[player_idx]
    events: list[dict] = []

    if action.kind == "wait":
        return events

    if action.kind == "build":
        cost = cfg.buildings[action.btype]["cost"]
        p.resources -= cost
        b = Building(
            uid=state.alloc_uid(),
            local_id=_next_local_id(p),
            owner=player_idx,
            btype=action.btype,
            hp=cfg.buildings[action.btype]["hp"],
            max_hp=cfg.buildings[action.btype]["hp"],
            slot=action.slot,
            pos=_slot_pos(cfg, action.slot, player_idx),
            birth_tick=state.tick,
        )
        p.slots[action.slot] = b
        events.append(
            {"type": "build", "player": player_idx, "building": action.btype,
             "slot": action.slot, "tick": state.tick}
        )

    elif action.kind == "tech":
        p.resources -= cfg.economy["tech_cost"]
        p.tech = 1
        p.tech_upgraded = True
        events.append(
            {"type": "tech", "player": player_idx, "level": 1, "tick": state.tick}
        )

    elif action.kind == "produce":
        B = p.barracks_count()
        batch = cfg.batch_size(action.utype, B)
        p.resources -= batch * cfg.units[action.utype]["price"]
        ucfg = cfg.units[action.utype]
        for _ in range(batch):
            p.units.append(
                Unit(
                    uid=state.alloc_uid(),
                    local_id=_next_local_id(p),
                    owner=player_idx,
                    utype=action.utype,
                    hp=ucfg["hp"],
                    birth_tick=state.tick,
                    slot=p.next_unit_slot(),
                )
            )
        events.append(
            {"type": "produce", "player": player_idx, "unit": action.utype,
             "count": batch, "tick": state.tick}
        )

    elif action.kind == "layout":
        a, b = action.slot, action.slot_b
        ba, bb = p.slots[a], p.slots[b]
        if ba is not None and bb is not None:
            ba.slot, bb.slot = b, a
            ba.pos, bb.pos = bb.pos, ba.pos
            p.slots[a], p.slots[b] = bb, ba
        elif ba is not None:
            p.slots[a], p.slots[b] = None, ba
            ba.slot = b
            ba.pos = _slot_pos(cfg, b, player_idx)
        else:
            p.slots[a], p.slots[b] = bb, None
            bb.slot = a
            bb.pos = _slot_pos(cfg, a, player_idx)
        p.layout_used = True
        events.append(
            {"type": "layout", "player": player_idx, "slots": [a, b],
             "tick": state.tick}
        )

    elif action.kind == "repair":
        target = p.hq if action.slot is None else p.slots[action.slot]
        p.resources -= cfg.economy["repair_cost"]
        healed = min(cfg.economy["repair_amount"], target.max_hp - target.hp)
        target.hp += healed
        p.repair_used = True
        events.append(
            {"type": "repair", "player": player_idx,
             "target": "hq" if action.slot is None else f"slot{action.slot}",
             "healed": healed, "tick": state.tick}
        )

    elif action.kind == "deploy":
        pool = sorted(p.reserve_of(action.utype), key=lambda u: u.local_id)
        take = pool[: cfg.limits["deploy_batch"]]
        pos = _deploy_pos(cfg, action.route, player_idx)
        for u in take:
            u.on_field = True
            u.pos = pos
            if cfg.rules_version != "game-rules-v0.1":
                if u.utype == "dog":
                    node_idx = 0 if action.route != 2 else 1
                    u.objective = state.nodes[node_idx].pos
                else:
                    u.objective = state.players[1 - player_idx].hq.pos
        p.deploy_used += 1
        events.append(
            {"type": "deploy", "player": player_idx, "unit": action.utype,
             "count": len(take), "route": ROUTES[action.route], "tick": state.tick}
        )

    elif action.kind == "signal":
        p.resources -= cfg.signal["cost"]
        center = region_center_local(action.region, cfg)
        p.signal_center = cfg.to_world(center, player_idx)
        p.signal_until_e = state.phase_e + cfg.signal["duration_ticks"]
        events.append(
            {"type": "signal", "player": player_idx, "center": p.signal_center,
             "tick": state.tick}
        )

    elif action.kind == "bomb":
        p.resources -= cfg.bomb["cost"]
        p.bomb_used = True
        center = region_center_local(action.region, cfg)
        world = cfg.to_world(center, player_idx)
        land_tick = state.tick + cfg.bomb["delay_ticks"]
        state.bombs.append(
            BombState(
                owner=player_idx,
                center=world,
                land_tick=land_tick,
                damage=cfg.bomb_damage(p.tech),
            )
        )
        events.append(
            {"type": "bomb_warning", "player": player_idx, "center": world,
             "land_tick": land_tick, "tick": state.tick}
        )
    return events


# ---- 小工具 ---------------------------------------------------------------


def _slot_pos(cfg: BalanceConfig, slot: int, player_idx: int) -> tuple[int, int]:
    raw = tuple(cfg.map_data["slots"][slot])
    return raw if player_idx == 0 else cfg.to_world(raw, 1)


def _deploy_pos(cfg: BalanceConfig, route: int, player_idx: int) -> tuple[int, int]:
    raw = tuple(cfg.map_data["deploys"][route])
    return raw if player_idx == 0 else cfg.to_world(raw, 1)


def _next_local_id(p: PlayerState) -> int:
    used = [b.local_id for b in p.buildings()] + [u.local_id for u in p.units]
    return (max(used) + 1) if used else 0
