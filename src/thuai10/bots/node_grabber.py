"""抢点脚本：机器狗快速占点，信号引导，节点收入滚雪球。"""
from __future__ import annotations

from ..core.config import BalanceConfig
from ..core.model import GameState
from .base import REGION_NORTH_MID, REGION_SOUTH_MID, Bot


class NodeGrabberBot(Bot):
    """优先生产/部署机器狗争抢两节点，其次信号与轰炸支援。"""

    name = "node_grabber"

    def __init__(self, seed: int = 0):
        super().__init__(seed)
        self.prefer_north = self.rng.random() < 0.5  # 有种子的开局选择

    def act(self, state: GameState, player: int, cfg: BalanceConfig):
        mask = self._legal(state, player, cfg)
        p = state.players[player]
        phase = state.phase

        if phase == "build":
            # 优先狗海；其次补兵营扩大批量；再次机器人
            return self._pick_first(
                [20, 2, 3, 21, 14, 8, 0], mask
            )

        if phase == "layout":
            # 把加农炮（初始槽 3）换到更靠近己方目标节点的一侧
            return self.layout_cannon(p, 1 if self.prefer_north else 5, mask)

        if phase == "repair":
            # 资源宽裕时修理受损建筑（优先总部）
            targets = [38] + [39 + i for i in range(6)]
            if p.resources >= cfg.economy["repair_cost"] + 30:
                best = self._most_damaged(p)
                if best is not None:
                    return self._pick_first([best] + [0], mask)
            return 0

        # attack
        # 根据已部署路线分流，避免连续把所有狗放在同一路。
        dogs = [u for u in p.units if u.on_field and u.utype == "dog"]
        first_route = (0 if self.prefer_north else 2) if not dogs else (2 if self.prefer_north else 0)
        deploy = self._pick_first([45+first_route, 49, 0], mask)
        if deploy:
            return deploy
        bomb = self.bomb_cluster(state, player, cfg, mask)
        if bomb:
            return bomb
        # 机器狗保持部署任务；不反复发信号将全军拉到一个节点。
        return 0

    @staticmethod
    def _most_damaged(p):
        best, best_gap = None, 0
        if p.hq is not None and 0 < p.hq.hp < p.hq.max_hp:
            best, best_gap = 38, p.hq.max_hp - p.hq.hp
        for i, b in enumerate(p.slots):
            if b is not None and 0 < b.hp < b.max_hp:
                gap = b.max_hp - b.hp
                if gap > best_gap:
                    best, best_gap = 39 + i, gap
        return best
