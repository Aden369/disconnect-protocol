"""快照、逐 tick 显示帧与状态校验值。

checksum 使用规范 JSON（排序键、整数数值）计算 SHA-256，是回放协议的一部分。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .config import BalanceConfig
from .endgame import score_display
from .model import GameState
from .nodes import controlled_count


def _entity_dict(e: Any, cfg: BalanceConfig, player: int) -> dict:
    from .model import Building, Unit

    if isinstance(e, Unit):
        lx, ly = (cfg.to_local(e.pos, player) if e.pos else (-1, -1))
        result = {
            "uid": e.uid,
            "local_id": e.local_id,
            "type": e.utype,
            "hp": e.hp,
            "max_hp": cfg.units[e.utype]["hp"],
            "on_field": e.on_field,
            "x": lx,
            "y": ly,
            "birth_tick": e.birth_tick,
        }
        if cfg.rules_version != "game-rules-v0.1":
            result.update(slot=e.slot, objective=list(cfg.to_local(e.objective, player)) if e.objective else None,
                          last_move_tick=e.last_move_tick, last_attack_tick=e.last_attack_tick)
        return result
    lx, ly = cfg.to_local(e.pos, player)
    result = {
        "uid": e.uid,
        "local_id": e.local_id,
        "type": e.btype,
        "hp": e.hp,
        "max_hp": e.max_hp,
        "slot": e.slot,
        "x": lx,
        "y": ly,
        "birth_tick": e.birth_tick,
    }
    if cfg.rules_version != "game-rules-v0.1":
        result["last_attack_tick"] = e.last_attack_tick
    return result


def snapshot(state: GameState, cfg: BalanceConfig) -> dict:
    """完整裁判状态（全信息 demo 与调试）。坐标为玩家本地坐标。"""
    players = []
    for i, p in enumerate(state.players):
        players.append(
            {
                "index": i,
                "resources": p.resources,
                "tech": p.tech,
                "tech_upgraded": p.tech_upgraded,
                "control_ticks": p.control_ticks,
                "control_seconds": p.control_ticks * cfg.nodes["control_seconds_per_tick"],
                "score": score_display(state, i, cfg),
                "deploy_used": p.deploy_used,
                "bomb_used": p.bomb_used,
                "layout_used": p.layout_used,
                "repair_used": p.repair_used,
                "hq": _entity_dict(p.hq, cfg, i),
                "slots": [
                    _entity_dict(b, cfg, i) if b is not None else None
                    for b in p.slots
                ],
                "units": [
                    _entity_dict(u, cfg, i) for u in sorted(p.units, key=lambda u: u.local_id)
                ],
                "signal": (
                    {
                        "center": list(cfg.to_local(p.signal_center, i)),
                        "until_e": p.signal_until_e,
                        "remaining": max(0, p.signal_until_e - state.phase_e),
                    }
                    if p.signal_center is not None
                    else None
                ),
            }
        )
    return {
        "config_version": cfg.version,
        "rules_version": cfg.rules_version,
        "obs_schema_version": cfg.obs_schema_version,
        "tick": state.tick,
        "round": state.round,
        "phase": state.phase,
        "phase_e": state.phase_e,
        "steps_taken": state.steps_taken,
        "players": players,
        "nodes": [
            {
                "index": n.index,
                "x": cfg.to_local(n.pos, 0)[0],
                "y": n.pos[1],
                "owner": n.owner,
                "progress": n.progress,
                "progress_player": n.progress_player,
            }
            for n in state.nodes
        ],
        "bombs": [
            {
                "player": b.owner,
                "center": list(cfg.to_local(b.center, 0)),
                "center_world": list(b.center),
                "land_tick": b.land_tick,
                "damage": b.damage,
                "ticks_until": max(0, b.land_tick - state.tick),
            }
            for b in state.bombs
        ],
        "winner": state.winner,
        "end_reason": state.end_reason,
    }


def frame(state: GameState, cfg: BalanceConfig) -> dict:
    """轻量逐 tick 显示帧：前端据此插值。坐标为世界坐标（渲染用）。"""
    units = []
    buildings = []
    for i, p in enumerate(state.players):
        for u in p.units:
            if u.on_field and u.pos is not None:
                units.append(
                    {
                        "uid": u.uid,
                        "player": i,
                        "type": u.utype,
                        "x": u.pos[0],
                        "y": u.pos[1],
                        "hp": u.hp,
                        "max_hp": cfg.units[u.utype]["hp"],
                    }
                )
        for b in p.buildings():
            buildings.append(
                {
                    "uid": b.uid,
                    "player": i,
                    "type": b.btype,
                    "x": b.pos[0],
                    "y": b.pos[1],
                    "hp": b.hp,
                    "max_hp": b.max_hp,
                }
            )
    return {
        "tick": state.tick,
        "round": state.round,
        "phase": state.phase,
        "phase_e": state.phase_e,
        "units": units,
        "buildings": buildings,
        "nodes": [
            {"index": n.index, "x": n.pos[0], "y": n.pos[1], "owner": n.owner,
             "progress": n.progress}
            for n in state.nodes
        ],
        "bombs": [
            {"player": b.owner, "x": b.center[0], "y": b.center[1],
             "land_tick": b.land_tick, "ticks_until": max(0, b.land_tick - state.tick)}
            for b in state.bombs
        ],
        "winner": state.winner,
        "players": snapshot(state, cfg)["players"],
        "end_reason": state.end_reason,
        "signals": [{"player": p.index, "x": p.signal_center[0], "y": p.signal_center[1],
                     "remaining": max(0, p.signal_until_e-state.phase_e)}
                    for p in state.players if p.signal_center is not None],
    }


def _canonical(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _canonical(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    return obj


def checksum(state: GameState, cfg: BalanceConfig) -> str:
    snap = snapshot(state, cfg)
    snap.pop("score", None)  # 由 HP 与控制 tick 决定，冗余
    for pl in snap.get("players", []):
        pl.pop("score", None)
    blob = json.dumps(_canonical(snap), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
