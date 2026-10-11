# 当前验证与限制

当前规则与协议v0.6；基于队友《智械边界》的设计借鉴见 [设计来源](idea-source.md)。

## 验证结果

- **119项pytest通过**，包括逐格信标/导弹、落点不匹配/越界掩码、EMP敌塔射速减半/友军不受影响、只读策略预测、同步结算、资源不判胜与历史回放兼容。
- **24种策略位置排列完成**：导弹8胜、堡垒8胜、破墙4胜、4平；平均与最长均170秒。
- **280次导弹发射/落地，累计292次地面单位命中**，命中次数可包含同一单位被不同导弹击中，不是独立击杀数量。与上一轮v0.5代表性回放的0次地面命中相比，逐格技能已参与实际地面交战；不同版本同时改变了策略和规则，不能仅归因于单项机制。
- **12局随机整数动作对战完成**：5局有冠军、7局平，最长170秒。这组随机策略仍用九宫整数，任意坐标路径由专项测试与脚本策略验证。
- v0.3/v0.4/v0.5历史回放兼容测试通过，v0.6结构化动作回放可复现。观测形状仍2681维，协议升至v0.6标记建筑冷却语义变化。

数据：[策略评测](../results/fourway-scripts-v0.6.json)、[随机对战](../results/fourway-random-v0.6.json)、[回放](../results/fourway-replay-v0.6.json)。历史靶场/前线试验见 [v0.5验证归档](archive/v0.5/validation.md)。

## 已知限制

电子战基线仍未取得冠军，多数比赛仍在过载阶段结束；新增机制不代表已完成竞技平衡。地面落点预测是基于当前交火与移动方向的启发式，目标离开或死亡后仍可能空弹；没有宣称保证命中。

当前策略是脚本，尚未训练强化学习模型。建筑布局固定，迫击炮/防空塔及已毁城墙没有重建动作。训练入口未注册为原生Gym/PettingZoo环境，迷雾、正式选手SDK、比赛部署及直接排名表尚未实现。

## 复现

```powershell
python -m pytest tests -q
python scripts/run_fourway.py --mode scripts --games 24 --out results/local/scripts.json --replay-out results/local/replay.json
python scripts/run_fourway.py --mode random --games 12 --out results/local/random.json
python scripts/experiment_ground_skills.py --rules v0.6
$env:PYTHONPATH="src"
python -m thuai10.core.replay results/fourway-replay-v0.6.json
```

使用 `--replay-out` 指定本地输出，避免覆盖已提交回放。GitHub自动测试运行同一pytest套件。
