"""终局判定：总部摧毁立即胜负（同 tick 双亡为平），六轮超时按节点分数评分。

超时分数 = 总部剩余 HP + 3 × 累计节点控制秒数（内部按整数 tick 计算：
2 × HP + 3 × control_ticks，比较等价）。同分平局。
"""
from __future__ import annotations

from typing import Optional

from .config import BalanceConfig
from .model import DRAW, GameState


def score_half_points(state: GameState, player_idx: int, cfg: BalanceConfig) -> int:
    """超时评分的二倍整数值：2×总部 HP + 3×控制 tick（= 2×(HP + 3×控制秒)）。"""
    p = state.players[player_idx]
    hq_hp = p.hq.hp if p.hq is not None else 0
    return 2 * hq_hp + cfg.nodes["score_per_control_second"] * p.control_ticks


def score_display(state: GameState, player_idx: int, cfg: BalanceConfig) -> float:
    """展示用分数：总部 HP + 3×控制秒。"""
    return score_half_points(state, player_idx, cfg) / 2.0


def check_hq_victory(state: GameState, cfg: BalanceConfig) -> list[dict]:
    """第 5 步末：任一总部归零立即终局；同 tick 双亡判平。"""
    dead = [
        i for i, p in enumerate(state.players) if p.hq is not None and p.hq.hp <= 0
    ]
    if not dead:
        return []
    if len(dead) == 2:
        state.winner = DRAW
    else:
        state.winner = 1 - dead[0]
    state.end_reason = "hq_destroyed"
    return [{"type": "victory", "winner": state.winner, "reason": state.end_reason,
             "tick": state.tick}]


def check_timeout(state: GameState, cfg: BalanceConfig) -> list[dict]:
    """六轮结束：按 HQ HP + 3×控制秒 比较。"""
    a = score_half_points(state, 0, cfg)
    b = score_half_points(state, 1, cfg)
    if a == b:
        state.winner = DRAW
    else:
        state.winner = 0 if a > b else 1
    state.end_reason = "timeout"
    return [{"type": "victory", "winner": state.winner, "reason": state.end_reason,
             "tick": state.tick}]
