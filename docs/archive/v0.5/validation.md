# v0.5 验证与地面技能试验（历史）

当前规则 v0.5，Git 基线 `v0.5.0`；统计针对29×29地图、四方实时模式。

## 验证结果

- **112项 pytest 通过**，包括旧双人回归、四方同步战斗、资源不判胜、兵种/防御分工、通信/制导、观测和历史回放兼容。
- **GitHub Actions 通过**，使用固定依赖和 Python 3.11 执行同一测试套件。
- **v0.5基线的24种策略位置排列完成**：导弹策略8胜、破墙策略4胜、12平局；平均170.33秒，最长172秒。
- **12局随机合法对战完成**：6局有冠军、6局平局，最长166秒。
- 主规则已逐项对照配置、程序与训练接口核对，地图和数值一致；总部受扰、信标生效、无人机跟随、176/178秒发弹边界、科技加成与结算位置的歧义已修正文案。

评测数据见 [策略排列](../../../results/fourway-scripts-v0.5.json)、[随机对战](../../../results/fourway-random-v0.5.json)；详细历史依据见 [基地验收](base-review-v0.5.md)和[规则核对](rules-audit-v0.5.md)。

## 已知限制

防御增强后平局增多，电子战基线仍弱，多数对局在过载阶段结束，竞技平衡未定稿。当前策略为脚本，尚未训练强化学习模型。

建筑布局固定；迫击炮、防空塔和已毁城墙没有重建动作。训练入口为本地并行接口，尚未注册为原生 Gym/PettingZoo 环境。迷雾、正式选手 SDK、比赛部署与直接排名表尚未实现。

## 复现

```powershell
python -m pytest tests -q
python scripts/run_fourway.py --mode scripts --games 24 --out results/local/scripts.json --replay-out results/local/replay.json
python scripts/run_fourway.py --mode random --games 12 --out results/local/random.json
$env:PYTHONPATH="src"
python -m thuai10.core.replay results/fourway-replay-v0.5.json
```

通过 `--replay-out` 指定本地输出，可避免覆盖已提交的示例回放。

## 地面技能试验

`python scripts/experiment_ground_skills.py` 在隔离靶场比较相同地面集群，关闭普通攻击，固定组保持位置；移动组允许目标正常执行信号移动。它验证机制，不代表真实对战胜率。

| 场景 | 地面有效伤害 | 命中/击杀 | 联网/信号指令 |
| --- | ---: | --- | --- |
| 不使用技能 | 0 | 0/0 | 3个目标保持联网和指令 |
| 导弹打固定集群 | 215 | 3/1 | 存活者正常联网 |
| EMP覆盖固定集群 | 0 | 0/0 | 3个目标全部断链、取消临时指令 |
| 导弹打移动集群 | 75 | 1/0 | 两个快速目标离开落点 |

导弹每目标伤害仍为75；215为65HP机器狗、110HP机甲及170HP破城机扣血之和。EMP不造成物理伤害、不是眩晕：地面单位仍按默认任务战斗，无人机受扰返航。

算法增加地面集群信标/打击与前线EMP选区；发射后不再替换自己的在途导弹信标。页面决策显示选择地面技能的原因。仍使用原有九宫与41动作，没有增加任意坐标或改变战斗规则。

改进策略的24种排列全部结束：堡垒12胜、导弹4胜、8平，平均168秒。一个代表性完整回放出现2次地面选区决策，但导弹实际地面命中为0，说明九宫固定落点和4秒飞行时间在正常对战中仍限制效果；不能把靶场伤害当作实战收益。后续应优先验证更细落点与驻守/交火目标预测，再决定是否修改规则。

数据：[隔离试验](../../../results/ground-skills-v0.5.json)、[完整对局](../../../results/frontline-scripts-v0.5.json)、[代表性技能决策](../../../results/frontline-decisions-v0.5.json)、[回放](../../../results/frontline-replay-v0.5.json)。
