"""脚本与随机合法策略。

四种脚本（抢点、防守、机器人推进、科技攻城）+ 随机合法代理；
预算不足时按预设优先级选择合法动作。
"""
from __future__ import annotations

from .base import Bot, RandomLegalBot
from .node_grabber import NodeGrabberBot
from .robot_push import RobotPushBot
from .siege_tech import TechSiegeBot
from .turtle import TurtleBot

BOTS = {
    "random_legal": RandomLegalBot,
    "node_grabber": NodeGrabberBot,
    "turtle": TurtleBot,
    "robot_push": RobotPushBot,
    "tech_siege": TechSiegeBot,
}

SCRIPT_BOTS = ("node_grabber", "turtle", "robot_push", "tech_siege")


def make_bot(name: str, seed: int = 0) -> Bot:
    if name not in BOTS:
        raise ValueError(f"未知策略 {name}，可选：{sorted(BOTS)}")
    return BOTS[name](seed=seed)


__all__ = [
    "Bot",
    "RandomLegalBot",
    "NodeGrabberBot",
    "TurtleBot",
    "RobotPushBot",
    "TechSiegeBot",
    "BOTS",
    "SCRIPT_BOTS",
    "make_bot",
]
