"""科技攻城脚本：首轮升科技，量产攻城车，轰炸破建筑，总部强攻。"""
from __future__ import annotations

from ..core.config import BalanceConfig
from ..core.model import GameState
from .base import REGION_ENEMY_HQ_NEAR, Bot


class TechSiegeBot(Bot):
    """第一轮升级科技，随后攻城车 + 机器人推进，信号与轰炸都指向敌方基地。"""

    name = "tech_siege"

    def act(self, state: GameState, player: int, cfg: BalanceConfig):
        mask = self._legal(state, player, cfg)
        p = state.players[player]
        phase = state.phase

        if phase == "build":
            if state.round == 0:
                return self._pick_first([19, 0], mask)  # 科技
            return self._pick_first([22, 21, 2, 20, 0], mask)

        if phase == "layout":
            return self.layout_cannon(p, 3, mask)

        if phase == "repair":
            if p.hq is not None and p.hq.hp < 400 and p.resources >= 40:
                return self._pick_first([38, 0], mask)
            return 0

        # attack：攻城车中路破防，信号/轰炸指向敌方基地
        deploy = self._pick_first([52, 49, 46, 0], mask)
        if deploy:
            return deploy
        bomb = self.bomb_cluster(state, player, cfg, mask)
        if bomb:
            return bomb
        return self.signal_to(state, player, cfg, REGION_ENEMY_HQ_NEAR, mask)
