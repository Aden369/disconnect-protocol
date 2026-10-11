"""双代理环境：浏览器、脚本与 RL 共用同一核心入口。

接口（对齐 PettingZoo Parallel 风格，首版不依赖 PettingZoo）：
    env = ComputeLandEnv(seed=0)
    observations, infos = env.reset(seed=0)
    observations, rewards, terminateds, truncateds, infos = env.step({"left": 0, "right": 0})

- 动作：双方各 Discrete(72)，动作字典见 thuai10.core.actions。
- 观测：固定形状 dict（见 observation.py），玩家本地坐标。
- 奖励：终局 胜 +1 / 负 -1 / 平 0，双方相反；中间奖励 0。
- terminated：对局自然终局（总部摧毁或六轮结束——规则上限是自然终局，
  不是训练器截断）；truncated 恒为 False。
- 非法动作按 WAIT 执行，并在 info["diagnostics"] 标注原因。
"""
from __future__ import annotations

from typing import Any, Optional, Union

from thuai10.core.actions import N_ACTIONS, legal_actions
from thuai10.core.config import BalanceConfig, load_config
from thuai10.core.engine import Game

from .observation import OBS_DIM, OBS_SCHEMA_VERSION, encode_observation, flatten_observation, obs_shapes

AGENTS = ("left", "right")
_PLAYER_INDEX = {"left": 0, "right": 1}


class ComputeLandEnv:
    """《算力领土》双代理并行提交环境。"""

    metadata = {"name": "ComputeLand-v0", "obs_schema_version": OBS_SCHEMA_VERSION}

    def __init__(self, seed: int = 0, config: Optional[Union[str, BalanceConfig]] = None):
        self.cfg = config if isinstance(config, BalanceConfig) else load_config(config)
        self.game = Game(self.cfg, seed=seed)
        self.agents: list[str] = list(AGENTS)
        self.seed = seed

    # ---- Gym 风格入口 -----------------------------------------------------

    def reset(self, seed: Optional[int] = None) -> tuple[dict, dict]:
        if seed is not None:
            self.seed = seed
        self.game.reset(seed=self.seed)
        self.agents = list(AGENTS)
        return self._observations(), self._infos()

    def step(self, actions: dict) -> tuple[dict, dict, dict, dict, dict]:
        a0 = actions.get("left", 0)
        a1 = actions.get("right", 0)
        out = self.game.step({"left": a0, "right": a1})
        rewards = {"left": 0.0, "right": 0.0}
        terminateds = {"left": False, "right": False}
        truncateds = {"left": False, "right": False}
        infos = self._infos()
        infos["events"] = out["events"]
        infos["frames"] = out["frames"]
        infos["diagnostics"] = out["illegal"]

        if out["done"]:
            winner = self.game.state.winner
            win = float(self.cfg.raw["reward"]["win"])
            loss = float(self.cfg.raw["reward"]["loss"])
            draw = float(self.cfg.raw["reward"]["draw"])
            if winner == -1:
                rewards = {"left": draw, "right": draw}
            else:
                rewards = {
                    "left": win if winner == 0 else loss,
                    "right": win if winner == 1 else loss,
                }
            terminateds = {"left": True, "right": True}
            self.agents = []
        observations = self._observations()
        return observations, rewards, terminateds, truncateds, infos

    def action_masks(self) -> dict:
        masks = self.game.legal_masks()
        return {"left": masks["left"], "right": masks["right"]}

    def observe(self) -> dict:
        return self._observations()

    # ---- 内部 -------------------------------------------------------------

    def _observations(self) -> dict:
        return {
            "left": encode_observation(self.game.state, 0, self.cfg),
            "right": encode_observation(self.game.state, 1, self.cfg),
        }

    def _infos(self) -> dict:
        masks = self.action_masks()
        return {
            "mask": masks,
            "state": self.game.snapshot(),
            "obs_schema_version": OBS_SCHEMA_VERSION,
        }

    # ---- 便捷工具（训练/测试） -------------------------------------------

    def flat(self, obs: dict) -> Any:
        return flatten_observation(obs)

    @staticmethod
    def shapes() -> dict:
        return obs_shapes()

    @staticmethod
    def obs_dim() -> int:
        return OBS_DIM

    @staticmethod
    def n_actions() -> int:
        return N_ACTIONS
