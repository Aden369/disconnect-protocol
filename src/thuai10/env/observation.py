"""观测编码：玩家本地坐标（我方在左），固定形状，schema 版本随配置发布。

各数组形状（float32）：
- grid       (11, 17, 5)：可走 / 北节点 / 南节点 / 部署点 / 总部
- public     (8,)：轮次、阶段 one-hot(4)、终局剩余 tick、双方累计控制 tick
- companies  (2, 13)：我/敌 资源、科技、部署次数、轰炸标记、布局/维修标记、
             总部 HP、距下次决策 tick、预备队三兵种数量、存活单位数
- buildings  (2, 7, 11) + buildings_mask (2, 7)：总部+六槽位；
             存在、类型 one-hot(4)、HP 比例、本地 x/y、炮塔冷却、出生 tick、本地 ID
- units      (2, 12, 16) + units_mask (2, 12)：存在、场上标记、HP 比例、
             类型 one-hot(3)、本地 x/y、位置有效、攻击/移动冷却、出生序号、任务 x/y 和有效标记、出生 tick
- nodes      (2, 7)：每节点 中立/我/敌 one-hot(3) + 占领进度 + 进度所属方 one-hot(3)
- signals    (2, 4)：每方 生效标记、中心本地 x/y、剩余 tick
- bombs      (2, 4)：每方 待落标记、中心本地 x/y、落下倒计时

数值按规则上限归一化。观测 schema 版本见 config.obs_schema_version。
"""
from __future__ import annotations

import numpy as np

from ..core.config import BalanceConfig
from ..core.model import GameState

GRID_H = 11
GRID_W = 17
N_SLOTS = 7          # 总部 + 六槽位
N_UNIT_SLOTS = 12
C_GRID = 5
C_PUBLIC = 8
C_COMPANY = 13
C_BUILDING = 11
C_UNIT = 16
C_NODE = 7
C_SIGNAL = 4
C_BOMB = 4

OBS_SCHEMA_VERSION = "thuai10-obs-v0.2"


def ticks_to_next_decision(state: GameState, cfg: BalanceConfig) -> int:
    if state.phase == "attack":
        return cfg.attack_decision_ticks - (state.phase_e % cfg.attack_decision_ticks)
    return cfg.phase_ticks[state.phase] - state.phase_e


def encode_observation(state: GameState, player: int, cfg: BalanceConfig) -> dict:
    """编码 `player` 的本地观测（我方在左，敌方在右）。"""
    me = state.players[player]
    enemy = state.players[1 - player]
    w, h = cfg.width, cfg.height

    grid = np.zeros((h, w, C_GRID), dtype=np.float32)
    blocked = {b.pos for b in (me.buildings() + enemy.buildings())}
    for y in range(h):
        for x in range(w):
            if cfg.to_world((x, y), player) not in blocked:
                grid[y, x, 0] = 1.0
    for n in state.nodes:
        lx, ly = cfg.to_local(n.pos, player)
        grid[ly, lx, 1 + n.index] = 1.0
    for route in cfg.map_data["deploys"]:
        wx, wy = route
        grid[wy, wx, 3] = 1.0
    hq_w = cfg.to_local(me.hq.pos, player)
    grid[hq_w[1], hq_w[0], 4] = 1.0

    public = np.zeros(C_PUBLIC, dtype=np.float32)
    public[0] = state.round / cfg.rounds
    public[1 + ["build", "layout", "repair", "attack"].index(state.phase)] = 1.0
    public[5] = (cfg.total_ticks - state.tick) / cfg.total_ticks
    max_control = cfg.rounds * cfg.phase_ticks["attack"] * len(state.nodes)
    public[6] = me.control_ticks / max_control
    public[7] = enemy.control_ticks / max_control

    companies = np.zeros((2, C_COMPANY), dtype=np.float32)
    for row, pl in enumerate((me, enemy)):
        companies[row, 0] = pl.resources / cfg.economy["resource_cap"]
        companies[row, 1] = pl.tech
        companies[row, 2] = pl.deploy_used / cfg.limits["deploy_per_round"]
        companies[row, 3] = 1.0 if pl.bomb_used else 0.0
        companies[row, 4] = 1.0 if pl.layout_used else 0.0
        companies[row, 5] = 1.0 if pl.repair_used else 0.0
        companies[row, 6] = (pl.hq.hp if pl.hq else 0) / cfg.buildings["hq"]["hp"]
        companies[row, 7] = ticks_to_next_decision(state, cfg) / 10.0
        for k, ut in enumerate(("dog", "robot", "siege")):
            companies[row, 8 + k] = len(pl.reserve_of(ut)) / cfg.limits["max_units"]
        companies[row, 11] = pl.alive_unit_count() / cfg.limits["max_units"]
        companies[row, 12] = len(pl.units) / cfg.limits["max_units"]

    buildings = np.zeros((2, N_SLOTS, C_BUILDING), dtype=np.float32)
    buildings_mask = np.zeros((2, N_SLOTS), dtype=np.float32)
    types = ("hq", "barracks", "cannon", "shield")
    for row, pl in enumerate((me, enemy)):
        entries = [pl.hq] + list(pl.slots)
        for i, b in enumerate(entries):
            if b is None:
                continue
            buildings_mask[row, i] = 1.0
            feat = buildings[row, i]
            feat[0] = 1.0
            feat[1 + types.index(b.btype)] = 1.0
            feat[5] = b.hp / b.max_hp
            lx, ly = cfg.to_local(b.pos, player)
            feat[6] = lx / (w - 1)
            feat[7] = ly / (h - 1)
            if b.btype == "cannon":
                interval = cfg.buildings["cannon"]["attack_interval_ticks"]
                feat[8] = max(0, interval - (state.tick-b.last_attack_tick)) / interval
            feat[9] = b.birth_tick / cfg.total_ticks
            feat[10] = b.local_id / 32.0

    units = np.zeros((2, N_UNIT_SLOTS, C_UNIT), dtype=np.float32)
    units_mask = np.zeros((2, N_UNIT_SLOTS), dtype=np.float32)
    utypes = ("dog", "robot", "siege")
    tick = state.tick
    for row, pl in enumerate((me, enemy)):
        for u in pl.units:
            if u.slot < 0:
                continue
            feat = units[row, u.slot]
            units_mask[row, u.slot] = 1.0
            feat[0] = 1.0
            feat[1] = 1.0 if u.on_field else 0.0
            feat[2] = u.hp / cfg.units[u.utype]["hp"]
            feat[3 + utypes.index(u.utype)] = 1.0
            if u.on_field and u.pos is not None:
                lx, ly = cfg.to_local(u.pos, player)
                feat[6] = lx / (w - 1)
                feat[7] = ly / (h - 1)
                feat[8] = 1.0
            ucfg = cfg.units[u.utype]
            atk_ready = tick - u.last_attack_tick
            move_ready = tick - u.last_move_tick
            feat[9] = max(0, ucfg["attack_interval_ticks"] - atk_ready) / ucfg["attack_interval_ticks"]
            feat[10] = max(0, ucfg["move_interval_ticks"] - move_ready) / ucfg["move_interval_ticks"]
            feat[11] = u.local_id / 32.0
            if u.objective is not None:
                ox, oy = cfg.to_local(u.objective, player)
                feat[12:15] = (ox/(w-1), oy/(h-1), 1.0)
            feat[15] = u.birth_tick / cfg.total_ticks

    nodes = np.zeros((2, C_NODE), dtype=np.float32)
    for i, n in enumerate(state.nodes):
        if n.owner == -1:
            nodes[i, 0] = 1.0
        elif n.owner == player:
            nodes[i, 1] = 1.0
        else:
            nodes[i, 2] = 1.0
        nodes[i, 3] = n.progress / cfg.nodes["capture_ticks"]
        nodes[i, 4 + (0 if n.progress_player == -1 else 1 if n.progress_player == player else 2)] = 1.0

    signals = np.zeros((2, C_SIGNAL), dtype=np.float32)
    for row, pl in enumerate((me, enemy)):
        if pl.signal_center is not None and state.phase_e <= pl.signal_until_e:
            signals[row, 0] = 1.0
            lx, ly = cfg.to_local(pl.signal_center, player)
            signals[row, 1] = lx / (w - 1)
            signals[row, 2] = ly / (h - 1)
            signals[row, 3] = max(0, pl.signal_until_e - state.phase_e) / cfg.signal["duration_ticks"]

    bombs = np.zeros((2, C_BOMB), dtype=np.float32)
    for b in state.bombs:
        row = 0 if b.owner == player else 1
        bombs[row, 0] = 1.0
        lx, ly = cfg.to_local(b.center, player)
        bombs[row, 1] = lx / (w - 1)
        bombs[row, 2] = ly / (h - 1)
        bombs[row, 3] = max(0, b.land_tick - state.tick) / cfg.bomb["delay_ticks"]

    return {
        "grid": grid,
        "public": public,
        "companies": companies,
        "buildings": buildings,
        "buildings_mask": buildings_mask,
        "units": units,
        "units_mask": units_mask,
        "nodes": nodes,
        "signals": signals,
        "bombs": bombs,
    }


def obs_shapes() -> dict:
    return {
        "grid": (GRID_H, GRID_W, C_GRID),
        "public": (C_PUBLIC,),
        "companies": (2, C_COMPANY),
        "buildings": (2, N_SLOTS, C_BUILDING),
        "buildings_mask": (2, N_SLOTS),
        "units": (2, N_UNIT_SLOTS, C_UNIT),
        "units_mask": (2, N_UNIT_SLOTS),
        "nodes": (2, C_NODE),
        "signals": (2, C_SIGNAL),
        "bombs": (2, C_BOMB),
    }


def flatten_observation(obs: dict) -> np.ndarray:
    """按固定键序拼接为一维向量（形状 (OBS_DIM,)）。"""
    parts = [
        obs["grid"].reshape(-1),
        obs["public"],
        obs["companies"].reshape(-1),
        obs["buildings"].reshape(-1),
        obs["buildings_mask"].reshape(-1),
        obs["units"].reshape(-1),
        obs["units_mask"].reshape(-1),
        obs["nodes"].reshape(-1),
        obs["signals"].reshape(-1),
        obs["bombs"].reshape(-1),
    ]
    return np.concatenate(parts).astype(np.float32)


OBS_DIM = int(sum(int(np.prod(s)) for s in obs_shapes().values()))
