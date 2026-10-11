"""配置加载：configs/balance-v0.1.json 是数值唯一来源。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "balance-v0.2.json"

UNIT_TYPES = ("dog", "robot", "siege")
BUILDING_TYPES = ("barracks", "cannon", "shield")
PHASES = ("build", "layout", "repair", "attack")
ROUTES = ("north", "mid", "south")


@dataclass(frozen=True)
class BalanceConfig:
    """冻结的平衡配置；所有数值从 JSON 装载后不再修改。"""

    raw: dict[str, Any] = field(repr=False)

    @property
    def version(self) -> str:
        return self.raw["version"]

    @property
    def rules_version(self) -> str:
        return self.raw["rules_version"]

    @property
    def schema_version(self) -> str:
        return self.raw["schema_version"]

    @property
    def obs_schema_version(self) -> str:
        return self.raw["obs_schema_version"]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    # 地图
    @property
    def width(self) -> int:
        return self.raw["map"]["width"]

    @property
    def height(self) -> int:
        return self.raw["map"]["height"]

    @property
    def mirror_x(self) -> int:
        return self.raw["map"]["mirror_x"]

    def to_world(self, local_xy: tuple[int, int], player: int) -> tuple[int, int]:
        """玩家本地坐标（我方在左）转世界坐标；右方映射 x -> mirror_x - x。"""
        x, y = local_xy
        return (x if player == 0 else self.mirror_x - x, y)

    def to_local(self, world_xy: tuple[int, int], player: int) -> tuple[int, int]:
        x, y = world_xy
        return (x if player == 0 else self.mirror_x - x, y)

    # 时间
    @property
    def rounds(self) -> int:
        return self.raw["time"]["rounds"]

    @property
    def phase_ticks(self) -> dict[str, int]:
        return self.raw["time"]["phase_ticks"]

    @property
    def attack_decision_ticks(self) -> int:
        return self.raw["time"]["attack_decision_ticks"]

    @property
    def total_ticks(self) -> int:
        pt = self.phase_ticks
        return self.rounds * (pt["build"] + pt["layout"] + pt["repair"] + pt["attack"])

    @property
    def decisions_per_round(self) -> int:
        return 3 + self.raw["time"]["attack_decisions"]

    @property
    def max_steps(self) -> int:
        return self.rounds * self.decisions_per_round

    # 数值便捷访问
    @property
    def units(self) -> dict[str, Any]:
        return self.raw["units"]

    @property
    def buildings(self) -> dict[str, Any]:
        return self.raw["buildings"]

    @property
    def economy(self) -> dict[str, Any]:
        return self.raw["economy"]

    @property
    def limits(self) -> dict[str, Any]:
        return self.raw["limits"]

    @property
    def nodes(self) -> dict[str, Any]:
        return self.raw["nodes"]

    @property
    def signal(self) -> dict[str, Any]:
        return self.raw["signal"]

    @property
    def bomb(self) -> dict[str, Any]:
        return self.raw["bomb"]

    @property
    def map_data(self) -> dict[str, Any]:
        return self.raw["map"]

    def unit_damage(self, unit_type: str, tech: int, vs_building: bool) -> int:
        u = self.units[unit_type]
        if vs_building:
            dmg = u["damage_building"]
            if unit_type == "siege" and tech >= 1:
                dmg = self.raw["combat"]["siege_damage_tech1_building"]
            return dmg
        return u["damage"]

    def cannon_damage(self, tech: int) -> int:
        c = self.buildings["cannon"]
        return c["damage_tech1"] if tech >= 1 else c["damage"]

    def bomb_damage(self, tech: int) -> int:
        b = self.bomb
        return b["damage_tech1"] if tech >= 1 else b["damage"]

    def batch_size(self, unit_type: str, barracks_count: int) -> int:
        return self.units[unit_type]["batch_per_barracks"] * barracks_count


def load_config(path: str | Path | None = None) -> BalanceConfig:
    p = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with open(p, encoding="utf-8") as f:
        return BalanceConfig(json.load(f))
