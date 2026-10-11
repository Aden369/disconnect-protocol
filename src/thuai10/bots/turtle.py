"""防守脚本：炮塔与护盾加固，维修优先，陆军拦截，囤资源打反击。"""
from __future__ import annotations

from ..core.config import BalanceConfig
from ..core.model import GameState
from .base import REGION_OWN_HQ_NEAR, Bot


class TurtleBot(Bot):
    """优先维修与防御建筑，出机器人守中路，敌军压近时轰炸己方半场。"""

    name = "turtle"

    def act(self, state: GameState, player: int, cfg: BalanceConfig):
        mask = self._legal(state, player, cfg)
        p = state.players[player]
        phase = state.phase

        if phase == "build":
            # 维修由 repair 阶段负责；这里补防御与兵力
            return self._pick_first(
                [8, 14, 9, 2, 21, 20, 0], mask
            )  # 加农炮/护盾/第二炮/兵营/机器人/狗

        if phase == "layout":
            # 把加农炮换到中路槽位（2/3），覆盖总部前沿
            return self.layout_cannon(p, 3, mask)

        if phase == "repair":
            best = self._most_damaged(p)
            if best is not None and p.resources >= cfg.economy["repair_cost"]:
                return self._pick_first([best, 0], mask)
            return 0

        # attack：敌方单位压近时优先防守
        enemy_units = [
            u for u in state.players[1 - player].units if u.on_field
        ]
        near_home = 0
        for u in enemy_units:
            lx, _ = cfg.to_local(u.pos, player)
            if lx <= 6:
                near_home += 1
        deploy = self._pick_first([49, 45, 47, 0], mask)
        if deploy:
            return deploy
        bomb = self.bomb_cluster(state, player, cfg, mask)
        if near_home:
            return bomb or self.signal_to(state, player, cfg, REGION_OWN_HQ_NEAR, mask)
        return bomb

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
