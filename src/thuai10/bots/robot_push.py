"""机器人推进脚本：机器人主力走中路，信号压向敌方总部。"""
from __future__ import annotations

from ..core.config import BalanceConfig
from ..core.model import GameState
from .base import REGION_ENEMY_HQ_NEAR, Bot


class RobotPushBot(Bot):
    """批量生产机器人并沿中路推进，信号指向敌方总部，轰炸破防。"""

    name = "robot_push"

    def __init__(self, seed: int = 0):
        super().__init__(seed)
        self.flank = self.rng.choice(("north", "south"))  # 有种子的开局选择

    def act(self, state: GameState, player: int, cfg: BalanceConfig):
        mask = self._legal(state, player, cfg)
        p = state.players[player]
        phase = state.phase

        if phase == "build":
            return self._pick_first([21, 2, 20, 3, 0], mask)

        if phase == "layout":
            return self.layout_cannon(p, 3, mask)

        if phase == "repair":
            if p.hq is not None and p.hq.hp < 350 and p.resources >= 40:
                return self._pick_first([38, 0], mask)
            return 0

        flank_deploy = 48 if self.flank == "north" else 50   # 机器人北/南
        deploy = self._pick_first([49, flank_deploy, 45, 0], mask)
        if deploy:
            return deploy
        bomb = self.bomb_cluster(state, player, cfg, mask)
        if bomb:
            return bomb
        return self.signal_to(state, player, cfg, REGION_ENEMY_HQ_NEAR, mask)
