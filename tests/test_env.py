"""M4 验收：观测形状固定、掩码含 WAIT、终局奖励相反、随机合法对局可终止。"""
from __future__ import annotations

import numpy as np

from thuai10.bots import make_bot
from thuai10.env import OBS_DIM, ComputeLandEnv, flatten_observation, obs_shapes


def test_obs_shapes_fixed():
    env = ComputeLandEnv(seed=0)
    obs, infos = env.reset(seed=0)
    shapes = obs_shapes()
    for side in ("left", "right"):
        for key, shape in shapes.items():
            assert obs[side][key].shape == shape
            assert obs[side][key].dtype == np.float32
            assert np.all(np.isfinite(obs[side][key]))
    flat = flatten_observation(obs["left"])
    assert flat.shape == (OBS_DIM,)
    for _ in range(10):
        obs, rewards, term, trunc, infos = env.step({"left": 0, "right": 0})
        for side in ("left", "right"):
            for key, shape in shapes.items():
                assert obs[side][key].shape == shape


def test_mask_always_includes_wait():
    env = ComputeLandEnv(seed=1)
    env.reset(seed=1)
    for _ in range(20):
        masks = env.action_masks()
        assert masks["left"][0] and masks["right"][0]
        assert len(masks["left"]) == 72
        obs, r, t, tr, info = env.step({"left": 0, "right": 0})
        if t["left"]:
            break


def test_terminal_rewards_opposite():
    env = ComputeLandEnv(seed=2)
    env.reset(seed=2)
    bot0 = make_bot("robot_push", seed=3)
    bot1 = make_bot("turtle", seed=4)
    done = False
    for _ in range(100):
        st = env.game.state
        obs, rewards, term, trunc, info = env.step(
            {"left": bot0.act(st, 0, env.cfg), "right": bot1.act(st, 1, env.cfg)}
        )
        if term["left"]:
            done = True
            assert term["right"] and not trunc["left"] and not trunc["right"]
            assert rewards["left"] == -rewards["right"], "终局奖励相反"
            winner = env.game.state.winner
            if winner == -1:
                assert rewards["left"] == 0.0
            elif winner == 0:
                assert rewards["left"] == 1.0 and rewards["right"] == -1.0
            else:
                assert rewards["left"] == -1.0 and rewards["right"] == 1.0
            break
    assert done, "对局应终止"


def test_illegal_action_runs_as_wait_with_diagnostics():
    env = ComputeLandEnv(seed=4)
    env.reset(seed=4)
    # 构建阶段提交进攻动作 45 → 非法 → WAIT，不扣资源
    res = env.game.state.players[0].resources
    obs, rewards, term, trunc, info = env.step({"left": 45, "right": 0})
    assert env.game.state.players[0].resources == res
    assert info["diagnostics"], "非法动作应有诊断标注"


def test_random_legal_games_all_terminate():
    """随机合法对战可全部终止（这里 20 局；100 局见 scripts/run_batch.py）。"""
    for seed in range(20):
        env = ComputeLandEnv(seed=seed)
        env.reset(seed=seed)
        bot0 = make_bot("random_legal", seed=seed * 2)
        bot1 = make_bot("random_legal", seed=seed * 2 + 1)
        for _ in range(100):
            st = env.game.state
            obs, rewards, term, trunc, info = env.step(
                {"left": bot0.act(st, 0, env.cfg), "right": bot1.act(st, 1, env.cfg)}
            )
            if term["left"]:
                break
        else:
            raise AssertionError(f"seed={seed} 未终止")
        assert env.game.state.tick <= 360


def test_obs_local_coords_mirror():
    """本地坐标：我方在左（local x = 世界 x 对左方；右方镜像）。"""
    env = ComputeLandEnv(seed=5)
    obs, _ = env.reset(seed=5)
    # 右方观测中我方总部应在本地 x=1（世界 15）
    hq_row_l = obs["left"]["buildings"][0, 0]
    hq_row_r = obs["right"]["buildings"][0, 0]
    assert abs(hq_row_l[6] * 16 - 1) < 1e-5
    assert abs(hq_row_r[6] * 16 - 1) < 1e-5, "右方本地坐标我方总部在 x_local=1"
