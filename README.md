# THUAI10《断链协议》四方演示

四家公司由四个算法实时交战。中继扩展指挥链路，信号弹引导军队并锁定导弹，EMP 屏蔽破坏通信和制导，陆军需要突破城墙。**最后存活者胜，资源从不参与判胜**。

当前主规则：[docs/game-rules.md](docs/game-rules.md)。当前验收：[docs/base-review-v0.5.md](docs/base-review-v0.5.md)；规则核对：[docs/rules-audit-v0.5.md](docs/rules-audit-v0.5.md)；历史v0.3 review：[docs/fourway-review.md](docs/fourway-review.md)。

## 运行

Python 3.11+。安装已验证的固定依赖：

```powershell
python -m pip install -r requirements-dev.txt
python scripts/serve.py --port 8000
```

打开 [本地演示](http://127.0.0.1:8000/)，自动开始四方对战。可选择四方策略、暂停、单步、倍速，旋转/缩放 3D 场景，点击部队/城墙查看状态。默认文字只标注核心与选中对象，避免遮住交战画面。Three.js 0.186.1 已放在 `web/vendor/`，运行不依赖在线 CDN。

## 验证与回放

```powershell
python -m pytest tests -q
python scripts/run_fourway.py --mode scripts --games 24 --out results/fourway-scripts-v0.5.json
python scripts/run_fourway.py --mode random --games 100 --out results/fourway-random-v0.5.json
$env:PYTHONPATH="src"
python -m thuai10.core.replay results/fourway-replay-v0.5.json
```

脚本模式默认枚举四种策略的 24 种位置排列；当前脚本确定性执行，不把重复 seed 当作独立策略样本。随机模式使用有种子的随机合法策略。页面可导出当局回放。

## 四方 RL 接口

```python
from thuai10.fourway.env import FourWayEnv

env = FourWayEnv(seed=10)
observations, info = env.reset()
actions = {"p0": 0, "p1": 0, "p2": 0, "p3": 0}
observations, rewards, terminated, truncated, info = env.step(actions)
```

每方 `Discrete(41)`，`info["mask"]` 给出合法动作。观测为固定形状、全信息世界坐标，四方编号显式编码。单位离网继续旧指令，不强制等待。唯一胜者 +1、淘汰时 -1，无冠军的存活者 0；四方不是双人零和问题。本类为本地并行环境，尚非已注册的 PettingZoo 原生环境。

## 模块

- `src/thuai10/fourway/`：当前规则、指挥网络、战斗、四脚本、回放、RL 环境。
- `src/thuai10/server/`：本地 HTTP；默认 `mode=four`。
- `web/four.html`、`four-app.js`、`four-scene.js`：当前科技风 3D 观战。
- `configs/balance-v0.5.json`：当前数值。
- `tests/test_fourway.py`：资源不判胜、四方同步、墙/空军、制导反制、淘汰与旋转对照等。
- `docs/`：规则、设计来源、计划、实现说明与 review；`results/`：批量结果与回放。

`src/thuai10/core/`、旧双人策略和 `balance-v0.1/v0.2.json` 保留历史规则与回放兼容，不是默认比赛模式。旧文档以 `*-v0.2.md` 标记。

## 当前限度

已有四方自动对战与技能/城墙的真实结算、109 项测试和批量验证。策略仍是脚本，尚未训练 RL；位置排列中制导策略胜率偏高，初始平衡未定稿。正式选手 SDK、迷雾、多方策略评估和比赛部署仍待继续。

前端使用 Prettier 四空格；新 Python 模块使用 Ruff。不要格式化 `web/vendor/` 的第三方文件。

## 版本管理

当前 Git 基线为 `v0.5.0`，主分支 `main`。变更记录见 [CHANGELOG.md](CHANGELOG.md)，分支、标签与规则版本流程见 [版本管理说明](docs/version-management.md)。历史规则保留配置与回放，不追溯伪造旧版本 Git 提交或标签。GitHub Actions 自动执行 pytest。
