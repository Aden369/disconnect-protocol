# 实现说明与接口 Schema

> 历史归档（v0.2）：保留当时的规则与验证记录。当前有效规则见 [游戏规则](../../game-rules.md)，本文件不再跟随当前实现更新。

日期：2026-10-10。实现版本：`configs/balance-v0.2.json`（`schema_version = thuai10-replay-v0.1`，`obs_schema_version = thuai10-obs-v0.2`）。规则依据 [game-rules.md](game-rules-v0.2.md)，计划依据 [demo-plan.md](demo-plan-v0.2.md)。动作编号与观测字段一经发布不得静默改变含义。

## 1. 时间结构

| 项目 | 数值 |
| --- | --- |
| 仿真步长 | 0.5 秒 / tick |
| 对局 | 6 轮 × 60 tick = 360 tick（180 秒） |
| 每轮阶段 | 构建 10 tick（1 决策）→ 布局 6 tick（1 决策）→ 维修 4 tick（1 决策）→ 进攻 40 tick（10 决策，每 4 tick 一次） |
| 决策总数 | 6 × 13 = 78 步（每步同时提交双方动作） |
| 进攻局部时间 | e = 已完成进攻 tick 数 0..40；决策在 e=0,4,…,36，随后结算 e+1..e+4 |

节点控制时长内部记整数 tick（每 tick 1 个控制 tick = 0.5 控制秒），展示时换算。超时分数比较使用等价整数式 `2×总部HP + 3×控制tick`。

## 2. 动作字典 Discrete(72)

| 编号 | 含义 | 校验要点 |
| --- | --- | --- |
| 0 | WAIT | 所有阶段恒合法 |
| 1..6 | 建兵营 → 槽 0..5 | 槽空、非总部建筑 ≤4、兵营 ≤2、资源 ≥70 |
| 7..12 | 建加农炮 → 槽 0..5 | 同上，加农炮 ≤2，≥60 |
| 13..18 | 建护盾塔 → 槽 0..5 | 同上，护盾塔 ≤1，≥50 |
| 19 | 科技升级 | 整局一次，≥60 |
| 20 / 21 / 22 | 生产机器狗 / 机器人 / 攻城车 | B=存活兵营数；批量 2B/2B/B；攻城车需科技 1；整批付得起且 人口+批量 ≤12 |
| 23..37 | 槽位对 (0,1),(0,2)…(4,5) | 每轮一次；双空非法；单方有建筑=移动，双方=交换 |
| 38 | 维修总部 | 每轮一次，≥20，修 80 不超上限，满血/已毁非法 |
| 39..44 | 维修槽 0..5 | 同上 |
| 45..47 | 部署机器狗 → 北/中/南 | 每轮 ≤3 次；预备队有该兵种；一次 min(3, 可用) 低 ID 优先 |
| 48..50 | 部署机器人 → 北/中/南 | 同上 |
| 51..53 | 部署攻城车 → 北/中/南 | 同上 |
| 54..62 | 信号 9 区域 | ≥5；区域按本地 y=2,5,8 每行 x=2,8,14；覆盖旧信号；生效 16 tick |
| 63..71 | 轰炸 9 区域 | ≥30，每轮一次；e+4 落下，半径 1，伤害 30（科技 1 为 40），不伤己方 |

区域编号 = `row×3 + col`（row 按 y=2,5,8，col 按 x=2,8,14）。右方动作执行前映射 `x → 16-x`。非法或缺失动作按 WAIT 执行，不扣款，`info["diagnostics"]` 记录原因。

## 3. 观测 Schema（thuai10-obs-v0.2）

玩家本地坐标（我方在左，右方 `x→16-x`）。全部 float32，按规则上限归一化：

| 键 | 形状 | 字段 |
| --- | --- | --- |
| `grid` | (11,17,5) | 可走 / 北节点 / 南节点 / 部署点 / 总部 |
| `public` | (8,) | 轮次/6、阶段 one-hot(4)、剩余 tick/360、双方控制 tick/480 |
| `companies` | (2,13) | 我/敌：资源/300、科技、部署/3、轰炸标记、布局标记、维修标记、总部 HP/500、距下次决策/10、预备队三兵种/12、存活单位/12、单位总数/12 |
| `buildings` | (2,7,11) | 总部+六槽位：存在、类型 one-hot(hq/兵营/炮/盾)、HP 比例、本地 x/16、y/10、炮塔攻击冷却余量、出生 tick/360、本地 ID/32 |
| `buildings_mask` | (2,7) | 建筑存在标记 |
| `units` | (2,12,16) | 槽位 0..11（存活稳定、死后复用）：存在、场上、HP 比例、类型 one-hot(3)、本地 x/16、y/10、位置有效、攻击冷却余量/间隔、移动冷却余量/间隔、出生序号/32、默认目标本地 x/y、目标有效标记、出生 tick/360 |
| `units_mask` | (2,12) | 单位存在标记 |
| `nodes` | (2,7) | 每节点：中立/我/敌 one-hot(3)、进度/4、进度所属方 one-hot(中立/我/敌) |
| `signals` | (2,4) | 每方：生效、中心本地 x/y、剩余/16 |
| `bombs` | (2,4) | 每方：待落、中心本地 x/y、倒计时/4 |

拼接顺序即上表顺序，`flatten_observation` 得到固定一维向量（`OBS_DIM = 1575`）。计时器（信号剩余、轰炸倒计时、决策距离、冷却）均显式编码。

## 4. RL 环境接口（thuai10.env.ComputeLandEnv）

```python
env = ComputeLandEnv(seed=0)
observations, infos = env.reset(seed=0)          # {"left": {...}, "right": {...}}
observations, rewards, terminateds, truncateds, infos = env.step({"left": a0, "right": a1})
```

- `infos["mask"]`：双方 72 维合法掩码，恒含 WAIT。
- `rewards`：终局 胜 +1 / 负 -1 / 平 0，双方相反；中间奖励 0。
- `terminateds`：总部摧毁或六轮结束（规则上限为自然终局，非截断）；`truncateds` 恒 False。
- 非法动作按 WAIT 执行，`infos["diagnostics"]` 标注。
- 后续 PettingZoo Parallel API 适配属可选扩展，需按官方版本接口另行核对。

## 5. 回放 Schema（thuai10-replay-v0.1）

```json
{
  "schema_version": "thuai10-replay-v0.1",
  "rules_version": "game-rules-v0.2",
  "config_version": "balance-v0.2",
  "config": { ...完整配置... },
  "seed": 0,
  "actions": [[a0, a1], ...],
  "checks": ["<每步后状态 SHA-256>", ...],
  "final": {"winner", "end_reason", "steps", "ticks", "scores"},
  "meta": {}
}
```

校验：`python -m thuai10.core.replay results/replay-example.json`。状态校验值取规范 JSON（排序键）的 SHA-256；同动作序列回放必须逐决策一致。稳定实体 ID（全局 uid + 每方 local_id）与固定遍历顺序（玩家 0/1，各按 local_id）属回放协议。

## 6. 确定性与结算顺序

每 tick（进攻阶段）：① 决策边界执行双方指令（非法→WAIT）；② 基于起始状态选择攻击/移动；③ 同时提交移动，按②的伤害加本 tick 到期轰炸（轰炸命中新位置）；④ 经护盾（tick 开始时存活的塔，每来源减 8 最低 1）汇总同时扣血并移除死亡实体（死者仍打出已选攻击）；⑤ 死亡移除后结算节点占领与控制时长，再判总部胜负（同 tick 双亡判平），进攻末撤军（保留 HP、冷却归零）。

同 seed 同动作序列 → 完全一致的回放与状态哈希（`tests/test_replay.py::test_same_seed_same_replay`）。

## 7. 里程碑验收对照

| 验收项 | 位置 |
| --- | --- |
| 六轮 WAIT 恰好 360 tick、78 步 | `tests/test_m1_basics.py::test_all_wait_is_360_ticks_78_steps` |
| 基础收入五次；节点加成收入 | `test_basic_income_five_times` / `test_income_with_node_bonus` |
| 非法动作不扣款、人口/建筑上限 | `test_illegal_*` / `test_building_caps` / `test_unit_cap_twelve` |
| 同 tick 双总部死亡判平 | `tests/test_m2_combat.py::test_both_hqs_die_same_tick_is_draw` |
| 死亡单位完成已选攻击 | `test_dead_unit_still_completes_selected_attack` |
| 最后一次轰炸在 tick 40 落下 | `test_bomb_lands_at_e_plus_4_last_at_40` |
| 死亡后不能占点 | `test_dead_units_cannot_capture` |
| 换边镜像一致 | `test_mirror_consistency_swap_sides` |
| 撤军保留单位 HP | `test_retreat_preserves_wounded_unit_hp` |
| 同动作回放完全一致 | `tests/test_replay.py::test_replay_roundtrip_identical` |
| 演示界面用真实核心状态、暂停/倍速不改结果 | 前端只调用 `step`；`tests/test_server.py` |
| §7 人工演示序列（含抢点/换位/维修/信号/轰炸） | `tests/test_demo_script.py` |
| 观测形状固定、掩码含 WAIT、终局奖励相反 | `tests/test_env.py` |
| 100 局随机合法全部结束 | `results/random-games.json`（100/100），另 `test_env.py` 20 局 |

## 8. v0.2 观战

默认 watch 模式，每步每方脚本调用一次，使用稳定的双方种子偏移。逐 tick 帧包含当时公司状态、双方信号、实际攻击与移动遥测、目标及事件。HUD、行为列表和场景使用同一帧；最后一帧播放完才结算。v0.1 旧回放继续使用旧默认目标逻辑及旧状态哈希；v0.2 哈希包含影响后续结算的冷却和默认任务。
