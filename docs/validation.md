# 当前验证与限制

当前规则 v0.5，Git 基线 `v0.5.0`；统计针对29×29地图、四方实时模式。

## 验证结果

- **109项 pytest 通过**，包括旧双人回归、四方同步战斗、资源不判胜、兵种/防御分工、通信/制导、观测和历史回放兼容。
- **GitHub Actions 通过**，使用固定依赖和 Python 3.11 执行同一测试套件。
- **24种策略位置排列完成**：导弹策略8胜、破墙策略4胜、12平局；平均170.33秒，最长172秒。
- **12局随机合法对战完成**：6局有冠军、6局平局，最长166秒。
- 主规则已逐项对照配置、程序与训练接口核对，地图和数值一致；总部受扰、信标生效、无人机跟随、176/178秒发弹边界、科技加成与结算位置的歧义已修正文案。

评测数据见 [策略排列](../results/fourway-scripts-v0.5.json)、[随机对战](../results/fourway-random-v0.5.json)；详细历史依据见 [基地验收](archive/v0.5/base-review-v0.5.md)和[规则核对](archive/v0.5/rules-audit-v0.5.md)。

## 已知限制

防御增强后平局增多，电子战基线仍弱，多数对局在过载阶段结束，竞技平衡未定稿。当前策略为脚本，尚未训练强化学习模型。

建筑布局固定；迫击炮、防空塔和已毁城墙没有重建动作。训练入口为本地并行接口，尚未注册为原生 Gym/PettingZoo 环境。迷雾、正式选手 SDK、比赛部署与直接排名表尚未实现。

## 复现

```powershell
python -m pytest tests -q
python scripts/run_fourway.py --mode scripts --games 24 --out results/local/scripts.json
python scripts/run_fourway.py --mode random --games 12 --out results/local/random.json
$env:PYTHONPATH="src"
python -m thuai10.core.replay results/fourway-replay-v0.5.json
```

批量脚本的策略模式会写入当前版本示例回放；运行后检查 Git 差异，确认是否保留示例回放更新。
