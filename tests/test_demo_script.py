"""M3 / §7 验收：三分钟展示脚本的预算与操作序列（人工演示步骤）。

对应 demo-plan §7：
1. 第一轮生产两个机器人，花 70、余 50；把加农炮换到北侧，维修跳过。
2. 初始机器狗走北路，机器人走中路，展示自动交火与占点。
3. 花 5 发信号集火，再花 30 轰炸集结区，余 15；显示预警与落点。
4. 第二轮解释上轮节点带来的收入。
"""
from __future__ import annotations

from thuai10.core import create_game
from thuai10.core.actions import SLOT_PAIRS


def test_demo_script_budget_and_flow():
    game = create_game(seed=1)
    p0 = game.state.players[0]

    # 1. 构建：生产两个机器人（B=1 → 2 只，70）
    out = game.step([21, 0])
    assert p0.resources == 50, "生产两个机器人花 70、余 50"
    produced = [e for e in out["events"] if e["type"] == "produce"]
    assert produced and produced[0]["count"] == 2 and produced[0]["unit"] == "robot"

    # 2. 布局：把加农炮换到北侧（槽 3 → 槽 1）
    aid = 23 + SLOT_PAIRS.index((1, 3))
    out = game.step([aid, 0])
    assert p0.slots[3] is None
    assert p0.slots[1] is not None and p0.slots[1].btype == "cannon"

    # 3. 维修：跳过
    game.step([0, 0])
    assert p0.resources == 50

    # 4. 进攻：机器狗走北路（e=0 决策）、机器人走中路（e=4 决策）
    out = game.step([45, 0])
    deploys = [e for e in out["events"] if e["type"] == "deploy"]
    assert deploys and deploys[0]["route"] == "north" and deploys[0]["unit"] == "dog"
    out = game.step([49, 0])
    deploys = [e for e in out["events"] if e["type"] == "deploy"]
    assert deploys and deploys[0]["route"] == "mid" and deploys[0]["unit"] == "robot"
    dogs = [u for u in p0.units if u.on_field and u.utype == "dog"]
    robots = [u for u in p0.units if u.on_field and u.utype == "robot"]
    assert len(dogs) == 2 and len(robots) == 3

    # 5. 花 5 发信号集火（指向北路交火区）
    game.step([54 + 1, 0])
    assert p0.resources == 45
    # 再花 30 轰炸集结区（北路敌方侧），余 15；预警与落点同块可见
    out = game.step([63 + 2, 0])
    assert p0.resources == 15, "花 5 信号 + 30 轰炸后余 15"
    warnings = [e for e in out["events"] if e["type"] == "bomb_warning"]
    bombs = [e for e in out["events"] if e["type"] == "bomb"]
    assert warnings, "轰炸预警可见（2 秒倒计时）"
    assert bombs, "轰炸在 e+4 落下"

    # 6. 结束第一轮：第二轮构建开始时结算节点收入
    incomes = []
    while game.state.round == 0 and not game.state.over:
        out = game.step([0, 0])
        incomes += [e for e in out["events"] if e["type"] == "income"]
    assert game.state.round == 1
    assert incomes, "第二轮构建开始前获得收入（含节点加成）"

    # 7. 第二轮维修演示：修理受损建筑（含总部），花 20 修 80
    while game.state.phase != "repair" and not game.state.over:
        game.step([0, 0])
    if p0.hq.hp == p0.hq.max_hp:
        p0.hq.hp -= 100  # 模拟上轮战损，演示维修取舍
    before = p0.resources
    out = game.step([38, 0])
    repairs = [e for e in out["events"] if e["type"] == "repair"]
    assert repairs and repairs[0]["healed"] == 80
    assert p0.resources == before - 20
    assert p0.hq.hp == 400 + 80  # 修 80 不超上限"
