"""四邻接 BFS 寻路：确定性、镜像一致。

用四邻接 BFS 找到离目标曼哈顿距离最小的可达格；候选终点同距时依次选
最短路径长度、本地 y、本地 x 较小者。最短路径等长时，按玩家本地坐标的
“前、北、南、后”邻格顺序确定下一步（前指向敌方；右方映射 x -> 16-x）。
"""
from __future__ import annotations

from collections import deque
from typing import Optional

from .config import BalanceConfig

Coord = tuple[int, int]


def neighbor_order(player: int) -> list[Coord]:
    """玩家本地方向顺序：前、北、南、后 → 世界坐标增量。北为 y 减小。"""
    # 本地：前 = +x_local，北 = -y，南 = +y，后 = -x_local
    if player == 0:
        return [(1, 0), (0, -1), (0, 1), (-1, 0)]
    return [(-1, 0), (0, -1), (0, 1), (1, 0)]


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def bfs_distance_map(
    start: Coord,
    walkable: set[Coord],
    cfg: BalanceConfig,
    player: int,
) -> dict[Coord, int]:
    """从 start 到各可达格的最短路径长度。start 恒视为可达。"""
    dist: dict[Coord, int] = {start: 0}
    q: deque[Coord] = deque([start])
    dirs = neighbor_order(player)
    w, h = cfg.width, cfg.height
    while q:
        cx, cy = q.popleft()
        d = dist[(cx, cy)]
        for dx, dy in dirs:
            nxt = (cx + dx, cy + dy)
            if nxt in dist:
                continue
            if not (0 <= nxt[0] < w and 0 <= nxt[1] < h):
                continue
            if nxt != start and nxt not in walkable:
                continue
            dist[nxt] = d + 1
            q.append(nxt)
    return dist


def best_endpoint(
    start: Coord,
    target: Coord,
    walkable: set[Coord],
    cfg: BalanceConfig,
    player: int,
) -> Coord:
    """离目标曼哈顿距离最小的可达格（含起点自身）。

    同距时依次选最短路径长度、本地 y、本地 x 较小者。
    """
    dist_map = bfs_distance_map(start, walkable, cfg, player)

    def key(cell: Coord) -> tuple:
        lx, ly = cfg.to_local(cell, player)
        return (manhattan(cell, target), dist_map[cell], ly, lx)

    return min(dist_map.keys(), key=key)


def next_step(
    start: Coord,
    target: Coord,
    walkable: set[Coord],
    cfg: BalanceConfig,
    player: int,
) -> Optional[Coord]:
    """从 start 走向 target 的一步；已是最优终点返回 None（原地等待）。

    只考虑最短路径；多条最短路径时按“前、北、南、后”邻格顺序取第一步。
    """
    d_start = bfs_distance_map(start, walkable, cfg, player)
    endpoint = min(
        d_start.keys(),
        key=lambda c: (
            manhattan(c, target),
            d_start[c],
            cfg.to_local(c, player)[1],
            cfg.to_local(c, player)[0],
        ),
    )
    if endpoint == start:
        return None
    d_end = bfs_distance_map(endpoint, walkable, cfg, player)
    total = d_start[endpoint]
    for dx, dy in neighbor_order(player):
        nxt = (start[0] + dx, start[1] + dy)
        if nxt not in d_start or nxt not in d_end:
            continue
        if d_start[nxt] + d_end[nxt] == total and d_end[nxt] == d_end[start] - 1:
            return nxt
    return None
