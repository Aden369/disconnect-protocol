"""自动战斗：目标选择、移动、炮塔开火、护盾减伤与同时结算。

每 tick：
1. 决策边界执行指令（engine 负责）。
2. 按本 tick 实体位置/HP/护盾状态选择攻击与移动。
3. 同时提交移动；按第 2 步位置与目标产生攻击伤害，加入本 tick 到期轰炸。
4. 汇总经护盾减免的伤害同时扣血，移除死亡实体（死者仍打出已选攻击）。
"""
from __future__ import annotations

from typing import Optional, Union

from .config import BalanceConfig
from .model import Building, GameState, Unit
from .pathing import manhattan, next_step

Coord = tuple[int, int]

# 选择结果：攻击（目标实体）/ 移动（新位置）/ 等待
AttackChoice = tuple[str, object, int]        # ("attack", target, damage)
MoveChoice = tuple[str, Coord]                # ("move", new_pos)
WaitChoice = tuple[str,]                      # ("wait",)
Choice = Union[AttackChoice, MoveChoice, WaitChoice]


def alive_units(state: GameState) -> list[Unit]:
    return [u for p in state.players for u in p.units if u.on_field]


def alive_buildings(state: GameState) -> list[Building]:
    return [b for p in state.players for b in p.buildings()]


def blocked_cells(state: GameState) -> set[Coord]:
    """本 tick 开始时仍存活的建筑格（含总部），下 tick 起被摧毁建筑可走。"""
    return {b.pos for b in alive_buildings(state)}


def walkable_cells(state: GameState, cfg: BalanceConfig) -> set[Coord]:
    blocked = blocked_cells(state)
    cells = {
        (x, y)
        for x in range(cfg.width)
        for y in range(cfg.height)
        if (x, y) not in blocked
    }
    return cells


def is_unit(entity: object) -> bool:
    return isinstance(entity, Unit)


def entity_pos(entity: object) -> Coord:
    return entity.pos


def shield_of(victim: Building, state: GameState, cfg: BalanceConfig) -> Optional[Building]:
    """tick 开始时存活的护盾塔中，保护 victim 的一座（不保护单位或自身）。"""
    aura = cfg.buildings["shield"]["aura_range"]
    for b in state.players[victim.owner].buildings():
        if b.btype != "shield" or b.uid == victim.uid:
            continue
        if manhattan(b.pos, victim.pos) <= aura:
            return b
    return None


def reduce_damage(
    damage: int, victim: object, state: GameState, cfg: BalanceConfig
) -> int:
    """每个攻击来源独立减伤：护盾减免 8，最低为 1。"""
    if isinstance(victim, Building):
        s = shield_of(victim, state, cfg)
        if s is not None:
            reduction = cfg.buildings["shield"]["reduction"]
            return max(cfg.buildings["shield"]["min_damage"], damage - reduction)
    return damage


def _target_key(entity: object, from_pos: Coord) -> tuple:
    return (manhattan(from_pos, entity.pos), entity.birth_tick, entity.local_id)


def select_unit_choice(
    state: GameState, unit: Unit, cfg: BalanceConfig, tick: int
) -> Choice:
    """单位每 tick 的行动选择。走一步后本 tick 不攻击。"""
    ucfg = cfg.units[unit.utype]
    enemy = state.players[1 - unit.owner]
    rng = ucfg["range"]

    enemies: list[object] = [
        u for u in enemy.units if u.on_field and manhattan(unit.pos, u.pos) <= rng
    ] + [
        b for b in enemy.buildings() if manhattan(unit.pos, b.pos) <= rng
    ]

    if enemies:
        # 射程内有敌人：停下攻击（或等冷却）；优先级见规则 7.1
        units_first = ucfg["priority"] == "units_first"

        def rank(e: object) -> tuple:
            return ((0 if is_unit(e) else 1) if units_first else (1 if is_unit(e) else 0),) + _target_key(e, unit.pos)

        target = min(enemies, key=rank)
        if tick - unit.last_attack_tick >= ucfg["attack_interval_ticks"]:
            damage = cfg.unit_damage(
                unit.utype, state.players[unit.owner].tech, not is_unit(target)
            )
            unit.last_attack_tick = tick
            return ("attack", target, damage)
        return ("wait",)

    # 射程内无敌人：移动
    move_iv = ucfg["move_interval_ticks"]
    if tick - unit.last_move_tick < move_iv:
        return ("wait",)
    target_cell = move_target(state, unit, cfg)
    walkable = walkable_cells(state, cfg)
    step = next_step(unit.pos, target_cell, walkable, cfg, unit.owner)
    if step is None:
        return ("wait",)
    unit.last_move_tick = tick
    return ("move", step)


def move_target(state: GameState, unit: Unit, cfg: BalanceConfig) -> Coord:
    """有效信号中心优先；否则最近非己方节点（等距取北）；均属己方则敌方总部。"""
    p = state.players[unit.owner]
    if p.signal_center is not None and state.phase_e <= p.signal_until_e:
        return p.signal_center
    if unit.objective is not None:
        return unit.objective
    non_own = [n for n in state.nodes if n.owner != unit.owner]
    if non_own:
        return min(non_own, key=lambda n: (manhattan(unit.pos, n.pos), n.index)).pos
    return state.players[1 - unit.owner].hq.pos


def select_cannon_choice(
    state: GameState, cannon: Building, cfg: BalanceConfig, tick: int
) -> Choice:
    """加农炮：每 2 tick 对射程内敌方单位攻击一次，不打建筑。"""
    c = cfg.buildings["cannon"]
    enemy = state.players[1 - cannon.owner]
    in_range = [
        u for u in enemy.units if u.on_field and manhattan(cannon.pos, u.pos) <= c["range"]
    ]
    if not in_range:
        return ("wait",)
    if tick - cannon.last_attack_tick < c["attack_interval_ticks"]:
        return ("wait",)
    target = min(in_range, key=lambda u: _target_key(u, cannon.pos))
    cannon.last_attack_tick = tick
    return ("attack", target, cfg.cannon_damage(state.players[cannon.owner].tech))


def collect_tick_choices(
    state: GameState, cfg: BalanceConfig, tick: int, activity: Optional[list] = None
) -> tuple[list[tuple[object, object, int]], list[tuple[Unit, Coord]]]:
    """第 2 步：全部实体基于同一状态选择行动。

    返回 (attacks, moves)：attacks 为 (攻击者, 目标, 伤害)，moves 为 (单位, 新位置)。
    遍历顺序：玩家 0/1，各按 local_id（回放协议的一部分）。
    """
    attacks: list[tuple[object, object, int]] = []
    moves: list[tuple[Unit, Coord]] = []
    for p in state.players:
        for b in sorted(p.buildings(), key=lambda x: x.local_id):
            if b.btype == "cannon":
                choice = select_cannon_choice(state, b, cfg, tick)
                if activity is not None:
                    activity.append(visual_choice(b, choice, state, cfg))
                if choice[0] == "attack":
                    attacks.append((b, choice[1], choice[2]))
        for u in sorted(p.units, key=lambda x: x.local_id):
            if not u.on_field:
                continue
            choice = select_unit_choice(state, u, cfg, tick)
            if activity is not None:
                activity.append(visual_choice(u, choice, state, cfg))
            if choice[0] == "attack":
                attacks.append((u, choice[1], choice[2]))
            elif choice[0] == "move":
                moves.append((u, choice[1]))
    return attacks, moves


def visual_choice(entity, choice, state, cfg):
    """渲染遥测来自实际选择结果，不参加策略或伤害结算。"""
    item = {"uid": entity.uid, "player": entity.owner, "kind": choice[0],
            "from": list(entity.pos)}
    if choice[0] == "attack":
        target = choice[1]
        item.update(target_uid=target.uid, target=list(target.pos), damage=choice[2],
                    label="攻击" + (target.utype if isinstance(target, Unit) else target.btype))
    elif isinstance(entity, Unit):
        target = move_target(state, entity, cfg)
        signal = state.players[entity.owner].signal_center is not None
        goal = "信号集结" if signal else ("守住算力节点" if entity.utype == "dog" else "进攻敌方总部")
        item.update(target=list(target), label=goal)
        if choice[0] == "move":
            item["next"] = list(choice[1])
        else:
            enemies = [u for u in state.players[1-entity.owner].units if u.on_field]
            enemies += state.players[1-entity.owner].buildings()
            in_range = any(manhattan(entity.pos, e.pos) <= cfg.units[entity.utype]["range"] for e in enemies)
            item["label"] = "装填 / 等待攻击" if in_range else (
                "驻守节点" if target == entity.pos else "移动冷却 / " + goal)
    else:
        item["label"] = "警戒 / 等待目标"
    return item
