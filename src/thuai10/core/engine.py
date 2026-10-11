"""确定性仿真引擎：决策边界执行双方动作，逐 tick 结算至下一决策点或终局。

`step(actions_by_player)` 同时提交双方 0..71 动作并推进到下一决策边界或提前终局；
`snapshot()` 返回完整裁判状态。回放一致性依赖稳定实体 ID 与固定遍历顺序。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional, Union

from . import actions as actions_mod
from .combat import alive_units, collect_tick_choices, reduce_damage
from .config import BalanceConfig, load_config
from .endgame import check_hq_victory, check_timeout, score_display
from .model import (
    DRAW,
    PHASE_ATTACK,
    PHASE_BUILD,
    Building,
    GameState,
    NodeState,
    PlayerState,
    Unit,
)
from .nodes import controlled_count, resolve_nodes

ActionPair = Union[dict, list, tuple]


class Game:
    """一局完整对局。浏览器、脚本与 RL 包装器共用此入口。"""

    def __init__(self, cfg: Optional[BalanceConfig] = None, seed: int = 0):
        self.cfg = cfg or load_config()
        self.seed = seed
        self.state = GameState()
        self.reset(seed=seed)

    # ---- 初始化 ----------------------------------------------------------

    def reset(self, seed: Optional[int] = None) -> dict:
        if seed is not None:
            self.seed = seed
        cfg = self.cfg
        st = GameState(tick=0, round=0, phase=PHASE_BUILD, phase_e=0, seed=self.seed)
        st.next_uid = 0
        for i in range(2):
            p = PlayerState(
                index=i,
                resources=cfg.economy["initial_resources"],
            )
            hq_pos = tuple(cfg.map_data["hq"][i])
            p.hq = Building(
                uid=st.alloc_uid(),
                local_id=0,
                owner=i,
                btype="hq",
                hp=cfg.buildings["hq"]["hp"],
                max_hp=cfg.buildings["hq"]["hp"],
                slot=None,
                pos=hq_pos,
            )
            init = cfg.raw["initial"]["buildings"]
            for btype, slot in init.items():
                b = Building(
                    uid=st.alloc_uid(),
                    local_id=_next_local(p),
                    owner=i,
                    btype=btype,
                    hp=cfg.buildings[btype]["hp"],
                    max_hp=cfg.buildings[btype]["hp"],
                    slot=slot,
                    pos=self._slot_world(slot, i),
                )
                p.slots[slot] = b
            for utype, count in cfg.raw["initial"]["reserve"].items():
                for _ in range(count):
                    p.units.append(
                        Unit(
                            uid=st.alloc_uid(),
                            local_id=_next_local(p),
                            owner=i,
                            utype=utype,
                            hp=cfg.units[utype]["hp"],
                            birth_tick=0,
                            slot=alloc_unit_slot(p),
                        )
                    )
            st.players.append(p)
        for idx, pos in enumerate(cfg.map_data["nodes"]):
            st.nodes.append(NodeState(index=idx, pos=tuple(pos)))
        self.state = st
        self.activity: list[dict] = []
        self.tick_events: list[dict] = []
        self.replay_actions: list[list[int]] = []
        self.replay_checks: list[str] = []
        return {"state": self.snapshot()}

    # ---- 决策步 ----------------------------------------------------------

    def step(self, actions: ActionPair) -> dict:
        """同时提交双方动作并推进到下一决策边界或提前终局。"""
        st = self.state
        if st.over:
            raise RuntimeError("对局已结束")
        a0, a1 = _unpack_actions(actions)

        # 双方基于同一旧状态校验；非法动作按 WAIT 执行
        v0 = actions_mod.validate(a0, st, 0, self.cfg)
        v1 = actions_mod.validate(a1, st, 1, self.cfg)
        events: list[dict] = []
        events += actions_mod.execute(a0 if v0 else 0, st, 0, self.cfg)
        events += actions_mod.execute(a1 if v1 else 0, st, 1, self.cfg)
        illegal = []
        if a0 is not None and not v0:
            illegal.append({"player": 0, "action": a0, "reason": "illegal_as_wait"})
        if a1 is not None and not v1:
            illegal.append({"player": 1, "action": a1, "reason": "illegal_as_wait"})

        frames: list[dict] = []
        n_ticks = self._decision_block_ticks()
        for _ in range(n_ticks):
            if st.over:
                break
            tick_events, frame = self._resolve_tick()
            events += tick_events
            frames.append(frame)

        st.steps_taken += 1
        self.replay_actions.append([int(a0 or 0), int(a1 or 0)])
        from .snapshot import checksum  # 局部导入避免循环

        self.replay_checks.append(checksum(st, self.cfg))
        return {
            "frames": frames,
            "events": events,
            "illegal": illegal,
            "done": st.over,
            "state": self.snapshot(),
        }

    def legal_masks(self) -> dict:
        return {
            "left": actions_mod.legal_actions(self.state, 0, self.cfg),
            "right": actions_mod.legal_actions(self.state, 1, self.cfg),
        }

    def snapshot(self) -> dict:
        from .snapshot import snapshot

        return snapshot(self.state, self.cfg)

    def scores(self) -> list[float]:
        return [
            score_display(self.state, 0, self.cfg),
            score_display(self.state, 1, self.cfg),
        ]

    # ---- tick 结算 -------------------------------------------------------

    def _decision_block_ticks(self) -> int:
        st = self.state
        if st.phase == PHASE_ATTACK:
            return self.cfg.attack_decision_ticks
        return self.cfg.phase_ticks[st.phase] - st.phase_e

    def _resolve_tick(self) -> tuple[list[dict], dict]:
        st = self.state
        st.tick += 1
        st.phase_e += 1
        events: list[dict] = []

        if st.phase == PHASE_ATTACK:
            self.activity = []
            events += self._resolve_attack_tick(st.tick)
            if st.over:
                self.tick_events = events
                return events, self._frame()
            if st.phase_e >= self.cfg.phase_ticks[PHASE_ATTACK]:
                events += self._end_of_round()
        else:
            self.activity = []
            # 前三阶段没有战斗，仅记录阶段时间
            if st.phase_e >= self.cfg.phase_ticks[st.phase]:
                order = ["build", "layout", "repair", "attack"]
                nxt = order[order.index(st.phase) + 1]
                st.phase = nxt
                st.phase_e = 0
        self.tick_events = events
        return events, self._frame()

    def _resolve_attack_tick(self, tick: int) -> list[dict]:
        st = self.state
        cfg = self.cfg
        events: list[dict] = []

        # 信号在完成 e+16 后失效（决策 e=phase_e 时生效至 phase_e+16）
        for p in st.players:
            if p.signal_center is not None and st.phase_e > p.signal_until_e:
                p.signal_center = None
                p.signal_until_e = -1

        # 第 2 步：基于本 tick 起始状态选择攻击与移动
        attacks, moves = collect_tick_choices(st, cfg, tick, self.activity)

        # 第 3 步：同时提交移动；攻击按第 2 步位置与目标产生伤害
        for unit, new_pos in moves:
            unit.pos = new_pos

        damage_pairs: list[tuple[object, int]] = []
        for attacker, target, dmg in attacks:
            damage_pairs.append((target, reduce_damage(dmg, target, st, cfg)))

        # 本 tick 到期轰炸（命中新位置）
        due = [b for b in st.bombs if b.land_tick == tick]
        for bomb in due:
            hit: list[dict] = []
            for p in st.players:
                if p.index == bomb.owner:
                    continue
                victims = [u for u in p.units if u.on_field] + p.buildings()
                for v in victims:
                    if _manhattan(v.pos, bomb.center) <= cfg.bomb["radius"]:
                        damage_pairs.append((v, reduce_damage(bomb.damage, v, st, cfg)))
                        hit.append({"kind": "unit" if isinstance(v, Unit) else "building",
                                    "local_id": v.local_id, "owner": v.owner})
            events.append(
                {"type": "bomb", "player": bomb.owner, "center": bomb.center,
                 "damage": bomb.damage, "hit": hit, "tick": tick}
            )
        if due:
            st.bombs = [b for b in st.bombs if b.land_tick != tick]

        # 第 4 步：汇总伤害同时扣血；移除死亡实体（死者仍打出已选攻击）
        totals: dict[int, int] = defaultdict(int)
        for victim, amount in damage_pairs:
            totals[victim.uid] += amount
        for entity in st.all_entities():
            if entity.uid in totals:
                entity.hp -= totals[entity.uid]
        for p in st.players:
            dead_units = [u for u in p.units if u.hp <= 0]
            for u in dead_units:
                events.append(
                    {"type": "unit_death", "player": p.index, "unit": u.utype,
                     "local_id": u.local_id, "pos": u.pos, "tick": tick}
                )
            p.units = [u for u in p.units if u.hp > 0]
            for slot in range(6):
                b = p.slots[slot]
                if b is not None and b.hp <= 0:
                    events.append(
                        {"type": "building_destroyed", "player": p.index,
                         "building": b.btype, "slot": slot, "pos": b.pos, "tick": tick}
                    )
                    p.slots[slot] = None

        # 第 5 步：节点占领与控制时长（死亡移除之后），再判总部胜负
        events += resolve_nodes(st, cfg, tick)
        events += check_hq_victory(st, cfg)
        return events

    def _end_of_round(self) -> list[dict]:
        st = self.state
        cfg = self.cfg
        events: list[dict] = []

        # 撤军：存活单位带当前 HP 返回预备队，冷却归零
        for p in st.players:
            for u in p.units:
                if u.on_field:
                    u.on_field = False
                    u.pos = None
                    u.objective = None
                u.last_move_tick = -10**9
                u.last_attack_tick = -10**9
            # 每轮重置：信号、部署/轰炸次数、炮塔冷却
            p.deploy_used = 0
            p.bomb_used = False
            p.layout_used = False
            p.repair_used = False
            p.signal_center = None
            p.signal_until_e = -1
            for b in p.buildings():
                b.last_attack_tick = -10**9
        for node in st.nodes:
            node.progress = 0
            node.progress_player = -1
        st.bombs = []
        events.append({"type": "round_end", "round": st.round, "tick": st.tick})

        if st.round >= cfg.rounds - 1:
            events += check_timeout(st, cfg)
            return events

        st.round += 1
        st.phase = PHASE_BUILD
        st.phase_e = 0
        # 第二至第六轮构建开始前获得收入
        if st.round + 1 >= cfg.economy["income_rounds_from"]:
            for p in st.players:
                nodes = controlled_count(st, p.index)
                income = cfg.economy["base_income"] + cfg.economy["node_income"] * nodes
                p.resources = min(cfg.economy["resource_cap"], p.resources + income)
                events.append(
                    {"type": "income", "player": p.index, "amount": income,
                     "nodes": nodes, "resources": p.resources, "tick": st.tick}
                )
        return events

    def _slot_world(self, slot: int, player: int) -> tuple[int, int]:
        raw = tuple(self.cfg.map_data["slots"][slot])
        return raw if player == 0 else self.cfg.to_world(raw, 1)

    def _frame(self) -> dict:
        from .snapshot import frame

        result = frame(self.state, self.cfg)
        result["activity"] = list(self.activity)
        result["events"] = list(self.tick_events)
        return result


def alloc_unit_slot(p: PlayerState) -> int:
    """观测单位槽位 0..11：存活期间稳定，死亡后复用。"""
    used = {u.slot for u in p.units}
    for i in range(12):
        if i not in used:
            return i
    return -1


def _next_local(p: PlayerState) -> int:
    used = [b.local_id for b in p.buildings()] + [u.local_id for u in p.units]
    return (max(used) + 1) if used else 0


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _unpack_actions(actions: ActionPair) -> tuple[Optional[int], Optional[int]]:
    if isinstance(actions, dict):
        a0 = actions.get("left", actions.get(0))
        a1 = actions.get("right", actions.get(1))
        return a0, a1
    seq = list(actions)
    return seq[0], seq[1]


def create_game(
    config: Optional[Union[str, BalanceConfig]] = None, seed: int = 0
) -> Game:
    cfg = config if isinstance(config, BalanceConfig) else load_config(config)
    return Game(cfg, seed=seed)
