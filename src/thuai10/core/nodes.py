"""节点占领与控制时长。

节点中心距离 ≤1 为占领范围；只有一方单位在范围内时连续维持 4 tick 取得控制；
争夺或空置清零进度、不改变归属。占领结算在死亡移除之后；每 tick 先更新归属，
再给控制方加控制时长（0.5 控制秒/tick，内部记整数 tick）。轮末进度归零。
"""
from __future__ import annotations

from .config import BalanceConfig
from .model import GameState, NodeState
from .pathing import manhattan


def resolve_nodes(state: GameState, cfg: BalanceConfig, tick: int) -> list[dict]:
    """第 5 步（死亡移除之后）：更新归属、累计控制时长。返回事件。"""
    events: list[dict] = []
    cap_range = cfg.nodes["capture_range"]
    cap_ticks = cfg.nodes["capture_ticks"]

    for node in state.nodes:
        counts = [0, 0]
        for p in state.players:
            for u in p.units:
                if u.on_field and manhattan(u.pos, node.pos) <= cap_range:
                    counts[u.owner] += 1
        if counts[0] > 0 and counts[1] == 0:
            exclusive = 0
        elif counts[1] > 0 and counts[0] == 0:
            exclusive = 1
        else:
            exclusive = -1  # 争夺或空置

        if exclusive < 0 or node.owner == exclusive:
            node.progress = 0
            node.progress_player = -1
        else:
            if node.progress_player == exclusive:
                node.progress += 1
            else:
                node.progress_player = exclusive
                node.progress = 1
            if node.progress >= cap_ticks:
                node.owner = exclusive
                node.progress = 0
                node.progress_player = -1
                events.append(
                    {"type": "node_flip", "player": exclusive, "node": node.index,
                     "pos": node.pos, "tick": tick}
                )

        if node.owner >= 0:
            state.players[node.owner].control_ticks += cfg.nodes["control_ticks_per_tick"]
    return events


def controlled_count(state: GameState, player_idx: int) -> int:
    return sum(1 for n in state.nodes if n.owner == player_idx)
