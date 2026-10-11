"""脚本策略基类：读取当前（旧）状态返回 0..71 动作。

预算不足时按预设优先级选择合法动作；`rng` 提供有种子的开局/路线选择，
保证同 seed 可复现、不同 seed 产生不同轨迹。
"""
from __future__ import annotations

import random
from typing import Optional

from ..core.actions import N_ACTIONS, legal_actions
from ..core.config import BalanceConfig
from ..core.model import GameState

# 区域编号（本地坐标）：y=2,5,8 每行 x=2,8,14
REGION_NORTH_MID = 1   # (8,2)
REGION_MID_MID = 4     # (8,5)
REGION_SOUTH_MID = 7   # (8,8)
REGION_ENEMY_HQ_NEAR = 5   # (14,5) 本地 → 敌方总部旁
REGION_OWN_HQ_NEAR = 3     # (2,5) 本地 → 己方总部旁
REGION_ROWS = {2: (0, 1, 2), 5: (3, 4, 5), 8: (6, 7, 8)}


class Bot:
    name = "bot"

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def act(self, state: GameState, player: int, cfg: BalanceConfig) -> Optional[int]:
        raise NotImplementedError

    def _legal(self, state: GameState, player: int, cfg: BalanceConfig) -> list[bool]:
        return legal_actions(state, player, cfg)

    def _pick_first(
        self, candidates: list[int], mask: list[bool], shuffle_first: int = 0
    ) -> Optional[int]:
        """按优先级返回第一个合法动作；前 shuffle_first 个候选用 rng 打乱。"""
        head = candidates[:shuffle_first]
        tail = candidates[shuffle_first:]
        self.rng.shuffle(head)
        for aid in head + tail:
            if 0 <= aid < N_ACTIONS and mask[aid]:
                return aid
        return 0  # WAIT

    def layout_cannon(self, p, slot, mask):
        from ..core.actions import SLOT_PAIRS
        if p.slots[slot] is not None and p.slots[slot].btype == "cannon":
            return 0
        for source, b in enumerate(p.slots):
            if b is not None and b.btype == "cannon":
                aid = 23 + SLOT_PAIRS.index(tuple(sorted((source, slot))))
                return aid if mask[aid] else 0
        return 0

    def signal_to(self, state, player, cfg, region, mask):
        from ..core.actions import region_center_local
        p = state.players[player]
        center = cfg.to_world(region_center_local(region, cfg), player)
        if not any(u.on_field for u in p.units):
            return 0
        if p.signal_center == center and p.signal_until_e - state.phase_e >= 4:
            return 0
        return 54 + region if mask[54 + region] else 0

    def bomb_cluster(self, state, player, cfg, mask):
        from ..core.actions import region_center_local
        from ..core.pathing import manhattan
        enemy = state.players[1-player]
        victims = [u for u in enemy.units if u.on_field] + enemy.buildings()
        best, value = 0, 0
        for region in range(9):
            if not mask[63+region]:
                continue
            center = cfg.to_world(region_center_local(region, cfg), player)
            hits = sum(1 for v in victims if manhattan(v.pos, center) <= cfg.bomb["radius"])
            if hits > value:
                best, value = 63+region, hits
        return best


class RandomLegalBot(Bot):
    """随机合法策略：在当前掩码内均匀采样（含 WAIT）。"""

    name = "random_legal"

    def act(self, state, player, cfg):
        mask = self._legal(state, player, cfg)
        legal = [i for i, ok in enumerate(mask) if ok]
        return self.rng.choice(legal)
