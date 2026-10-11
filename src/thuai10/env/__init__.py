"""双代理环境、观测编码和动作掩码。"""
from .env import AGENTS, ComputeLandEnv
from .observation import OBS_DIM, OBS_SCHEMA_VERSION, flatten_observation, obs_shapes

__all__ = [
    "AGENTS",
    "ComputeLandEnv",
    "OBS_DIM",
    "OBS_SCHEMA_VERSION",
    "flatten_observation",
    "obs_shapes",
]
