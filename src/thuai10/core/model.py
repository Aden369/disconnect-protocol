"""核心数据模型：单位、建筑、节点、轰炸、玩家与对局状态。

稳定实体 ID 与遍历顺序是回放协议的一部分：所有实体持有全局递增 `uid`
与按玩家本地递增的 `local_id`（结算排序用 local_id / birth_tick）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

NEUTRAL = -1
DRAW = -1

# 局内阶段常量（与 config.phase_ticks 键一致）
PHASE_BUILD = "build"
PHASE_LAYOUT = "layout"
PHASE_REPAIR = "repair"
PHASE_ATTACK = "attack"
PHASE_ORDER = (PHASE_BUILD, PHASE_LAYOUT, PHASE_REPAIR, PHASE_ATTACK)


@dataclass
class Unit:
    uid: int
    local_id: int
    owner: int
    utype: str            # dog / robot / siege
    hp: int
    birth_tick: int
    slot: int = -1        # 观测单位槽位 0..11；存活期间稳定，死亡后复用
    on_field: bool = False
    pos: Optional[tuple[int, int]] = None   # 世界坐标；预备队中为 None
    last_move_tick: int = -10**9            # 上次移动的 tick；初始可立即行动
    last_attack_tick: int = -10**9
    objective: Optional[tuple[int, int]] = None  # v0.2 部署时确定，信号暂时覆盖


@dataclass
class Building:
    uid: int
    local_id: int
    owner: int
    btype: str            # hq / barracks / cannon / shield
    hp: int
    max_hp: int
    slot: Optional[int]   # 槽位 0..5；总部为 None
    pos: tuple[int, int]  # 世界坐标
    birth_tick: int = 0
    last_attack_tick: int = -10**9          # 加农炮冷却


@dataclass
class NodeState:
    index: int            # 0=北 (8,2)，1=南 (8,8)
    pos: tuple[int, int]
    owner: int = NEUTRAL
    progress: int = 0
    progress_player: int = NEUTRAL


@dataclass
class BombState:
    owner: int
    center: tuple[int, int]     # 世界坐标
    land_tick: int              # 全局 tick（该 tick 结算时落下）
    damage: int


@dataclass
class PlayerState:
    index: int
    resources: int
    tech: int = 0
    tech_upgraded: bool = False
    hq: Optional[Building] = None
    slots: list[Optional[Building]] = field(default_factory=lambda: [None] * 6)
    units: list[Unit] = field(default_factory=list)
    control_ticks: int = 0                # 累计节点控制 tick（展示秒数 = tick/2）
    # 每轮重置
    deploy_used: int = 0
    bomb_used: bool = False
    layout_used: bool = False
    repair_used: bool = False
    signal_center: Optional[tuple[int, int]] = None
    signal_until_e: int = -1              # 进攻局部 e：完成 e 后失效

    def alive_unit_count(self) -> int:
        return len(self.units)

    def next_unit_slot(self) -> int:
        used = {u.slot for u in self.units}
        return next((i for i in range(12) if i not in used), -1)

    def barracks_count(self) -> int:
        return sum(1 for b in self.slots if b is not None and b.btype == "barracks")

    def building_count(self) -> int:
        return sum(1 for b in self.slots if b is not None)

    def reserve_of(self, utype: str) -> list[Unit]:
        return [u for u in self.units if not u.on_field and u.utype == utype]

    def buildings(self) -> list[Building]:
        out = []
        if self.hq is not None:
            out.append(self.hq)
        out.extend(b for b in self.slots if b is not None)
        return out


@dataclass
class GameState:
    tick: int = 0                 # 已完成 tick 数，0..360
    round: int = 0                # 0..5
    phase: str = PHASE_BUILD
    phase_e: int = 0              # 当前阶段已完成 tick 数
    steps_taken: int = 0          # 已执行的双方联合决策数
    players: list[PlayerState] = field(default_factory=list)
    nodes: list[NodeState] = field(default_factory=list)
    bombs: list[BombState] = field(default_factory=list)
    next_uid: int = 0
    winner: Optional[int] = None  # None=进行中，0/1=胜者，DRAW=平局
    end_reason: Optional[str] = None  # hq_destroyed / timeout
    seed: int = 0

    @property
    def over(self) -> bool:
        return self.winner is not None

    def alloc_uid(self) -> int:
        uid = self.next_uid
        self.next_uid += 1
        return uid

    def current_e(self) -> int:
        """当前决策点的进攻局部时间 e（仅攻击阶段有意义）。"""
        return self.phase_e

    def all_entities(self) -> list[object]:
        """确定性遍历顺序：先玩家 0 后玩家 1，各按 local_id。"""
        out: list[object] = []
        for p in self.players:
            out.extend(p.buildings())
            out.extend(sorted(p.units, key=lambda u: u.local_id))
        return out
