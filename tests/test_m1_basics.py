"""M1 验收：配置与初始化、72 动作与掩码、四阶段、收入、上限。"""
from __future__ import annotations

from thuai10.core import create_game
from thuai10.core.actions import N_ACTIONS, SLOT_PAIRS, legal_actions, validate
from thuai10.core.config import load_config
from thuai10.core.model import Unit

cfg = load_config()


def skip_to(game, round_no: int, phase: str):
    """WAIT 推进到指定轮次指定阶段的决策边界。"""
    while not game.state.over:
        if game.state.round == round_no and game.state.phase == phase:
            return
        game.step([0, 0])
    raise AssertionError("对局提前结束")


def test_all_wait_is_360_ticks_78_steps():
    game = create_game(seed=1)
    for _ in range(100):
        if game.state.over:
            break
        game.step([0, 0])
    assert game.state.tick == 360
    assert game.state.steps_taken == 78
    assert game.state.over
    assert game.state.end_reason == "timeout"
    assert game.state.winner == -1  # 500 HP 对 500 HP，平局


def test_basic_income_five_times():
    incomes = []
    game = create_game(seed=2)
    for _ in range(78):
        if game.state.over:
            break
        out = game.step([0, 0])
        incomes += [e for e in out["events"] if e["type"] == "income" and e["player"] == 0]
    assert len(incomes) == 5  # 第二至第六轮
    for ev in incomes:
        assert ev["amount"] == 60  # WAIT 对局无人占点
    assert game.state.players[0].resources == 300  # 120+300 封顶


def test_income_with_node_bonus():
    game = create_game(seed=3)
    skip_to(game, 0, "attack")
    events = game.step([45, 0])["events"]  # p0 部署狗到北路
    for _ in range(9):
        events += game.step([0, 0])["events"]
    assert any(n.owner == 0 for n in game.state.nodes), "狗应能占领中立节点"
    income = [e for e in events if e["type"] == "income"]
    assert len(income) == 2
    # 狗在占领后会继续奔向下一个非己方节点，占领数以事件为准
    assert income[0]["nodes"] >= 1
    assert income[0]["amount"] == 60 + 20 * income[0]["nodes"]
    assert income[1]["amount"] == 60


def test_illegal_action_no_charge():
    game = create_game(seed=4)
    before = game.state.players[0].resources
    game.step([0, 0])  # 构建 WAIT
    out = game.step([23 + SLOT_PAIRS.index((4, 5)), 0])  # 双方空位，非法
    assert game.state.players[0].resources == before
    assert out["illegal"]
    assert game.state.players[0].layout_used is False


def test_illegal_produce_when_broke():
    game = create_game(seed=5)
    game.state.players[0].resources = 10
    out = game.step([20, 0])  # 生产狗需 40，非法
    assert game.state.players[0].resources == 10
    assert len(game.state.players[0].units) == 3  # 初始 2 狗 1 机器人
    assert out["illegal"]


def test_build_action_charges_and_completes():
    game = create_game(seed=6)
    game.step([2, 0])  # 兵营建到空槽 1，70
    assert game.state.players[0].resources == 50
    b = game.state.players[0].slots[1]
    assert b is not None and b.btype == "barracks" and b.hp == 180
    assert game.state.players[0].barracks_count() == 2


def test_building_caps():
    game = create_game(seed=7)
    p = game.state.players[0]
    skip_to(game, 0, "build")
    game.step([2, 0])  # 兵营 → 槽 1（动作 1+k）
    skip_to(game, 1, "build")
    game.step([9, 0])  # 加农炮 → 槽 2
    assert p.building_count() == 4
    skip_to(game, 2, "build")
    mask = legal_actions(game.state, 0, cfg)
    assert not any(mask[1:19]), "非总部建筑最多 4 栋"
    game.step([13, 0])  # 非法 → WAIT
    assert p.building_count() == 4


def test_barracks_cap_two():
    game = create_game(seed=8)
    skip_to(game, 0, "build")
    game.step([2, 0])  # 兵营槽 1
    skip_to(game, 1, "build")
    game.step([3, 0])  # 兵营槽 2
    skip_to(game, 2, "build")
    mask = legal_actions(game.state, 0, cfg)
    assert not any(mask[1:7]), "兵营最多 2"


def test_unit_cap_twelve():
    game = create_game(seed=9)
    p = game.state.players[0]
    for i in range(9):  # 补足到 11 个单位（初始 3）
        p.units.append(
            Unit(uid=1000 + i, local_id=100 + i, owner=0, utype="dog", hp=60, birth_tick=0)
        )
    assert p.alive_unit_count() == 12
    skip_to(game, 0, "build")
    assert not legal_actions(game.state, 0, cfg)[20], "满员不可生产"
    p.units.pop()
    p.units.pop()
    assert p.alive_unit_count() == 10
    assert legal_actions(game.state, 0, cfg)[20], "死亡立即释放名额（10+2 恰好到上限）"


def test_tech_once_and_unlocks_siege():
    game = create_game(seed=10)
    p = game.state.players[0]
    skip_to(game, 0, "build")
    game.step([19, 0])
    assert p.tech == 1 and p.resources == 60
    skip_to(game, 1, "build")
    mask = legal_actions(game.state, 0, cfg)
    assert not mask[19], "科技整局最多一次"
    assert mask[22], "科技 1 解锁攻城车（B=1 → 1 辆 55）"
    assert not legal_actions(create_game(seed=10).state, 0, cfg)[22], "科技 0 不可生产攻城车"


def test_produce_batch_scales_with_barracks():
    game = create_game(seed=11)
    skip_to(game, 0, "build")
    game.step([2, 0])  # 第二兵营
    p = game.state.players[0]
    p.resources = 200
    skip_to(game, 1, "build")
    assert p.barracks_count() == 2
    before = len(p.units)
    assert legal_actions(game.state, 0, cfg)[20]
    game.step([20, 0])  # 狗 2B=4 只，80 资源
    assert len(p.units) == before + 4
    assert p.resources == 200 + 60 - 80  # 200 + 第二轮收入 60 − 生产 80
    # 一批 4 只需 80：79 不够则非法
    game2 = create_game(seed=11)
    p2 = game2.state.players[0]
    p2.resources = 79
    p2.slots[1] = p2.slots[0].__class__(
        uid=900, local_id=50, owner=0, btype="barracks", hp=180, max_hp=180,
        slot=1, pos=(3, 2))
    assert not validate(20, game2.state, 0, cfg)  # 2 兵营 → 4 只狗需 80 > 79


def test_deploy_limited_three_per_round():
    game = create_game(seed=12)
    skip_to(game, 0, "build")
    game.step([20, 0])  # 2 狗 → 共 4 狗 1 机器人
    skip_to(game, 0, "attack")
    p = game.state.players[0]
    for aid in (45, 45, 48):
        assert legal_actions(game.state, 0, cfg)[aid]
        game.step([aid, 0])
    assert not any(legal_actions(game.state, 0, cfg)[45:54]), "每轮最多三次部署"
    deployed = sum(1 for u in p.units if u.on_field)
    # 3 狗 + 1 狗 + 1 机器人（优先低 ID）
    assert deployed == 5


def test_deploy_batch_max_three():
    game = create_game(seed=13)
    skip_to(game, 0, "build")
    game.step([20, 0])
    skip_to(game, 0, "attack")
    out = game.step([45, 0])
    deploy = [e for e in out["events"] if e["type"] == "deploy"]
    assert deploy[0]["count"] == 3


def test_layout_swap_and_move():
    game = create_game(seed=14)
    p = game.state.players[0]
    barracks, cannon = p.slots[0], p.slots[3]
    skip_to(game, 0, "layout")
    game.step([23 + SLOT_PAIRS.index((1, 3)), 0])  # 移动：加农炮(3) → 空槽 1
    assert p.slots[3] is None
    assert p.slots[1] is cannon
    assert cannon.pos == (3, 2)
    skip_to(game, 1, "layout")
    game.step([23 + SLOT_PAIRS.index((0, 1)), 0])  # 交换：兵营(0) ↔ 加农炮(1)
    assert p.slots[0] is cannon and p.slots[1] is barracks
    assert cannon.pos == (2, 2) and barracks.pos == (3, 2)


def test_layout_once_per_round():
    game = create_game(seed=15)
    skip_to(game, 0, "layout")
    game.step([23 + SLOT_PAIRS.index((1, 3)), 0])
    assert not any(legal_actions(game.state, 0, cfg)[23:38])


def test_repair_rules():
    game = create_game(seed=16)
    p = game.state.players[0]
    skip_to(game, 0, "repair")
    assert not any(legal_actions(game.state, 0, cfg)[38:45]), "满血维修非法"
    p.hq.hp = 500 - 10
    mask = legal_actions(game.state, 0, cfg)
    assert mask[38]
    before = p.resources
    game.step([38, 0])
    assert p.resources == before - 20
    assert p.hq.hp == 500, "不超过生命上限"
    assert not any(legal_actions(game.state, 0, cfg)[38:45]), "每轮至多一次"


def test_repair_even_one_hp_costs_full():
    game = create_game(seed=17)
    skip_to(game, 0, "repair")
    game.state.players[0].hq.hp = 500 - 1
    game.step([38, 0])
    assert game.state.players[0].resources == 100
    assert game.state.players[0].hq.hp == 500


def test_destroyed_building_cannot_repair_but_rebuildable():
    game = create_game(seed=18)
    p = game.state.players[0]
    skip_to(game, 0, "repair")
    p.slots[3].hp = 0  # 模拟被摧毁（引擎会在战斗中移除，这里验证掩码逻辑）
    p.slots[3] = None
    mask = legal_actions(game.state, 0, cfg)
    assert not mask[38 + 3]  # 空槽不可修
    skip_to(game, 1, "build")
    assert legal_actions(game.state, 0, cfg)[7 + 3], "摧毁后可在构建阶段重建"


def test_mask_always_has_wait():
    game = create_game(seed=19)
    for _ in range(20):
        mask = legal_actions(game.state, 0, cfg)
        assert mask[0]
        assert len(mask) == N_ACTIONS
        game.step([0, 0])


def test_initial_state():
    game = create_game(seed=20)
    for i, p in enumerate(game.state.players):
        assert p.resources == 120
        assert p.tech == 0
        assert p.hq.hp == 500
        assert p.slots[0] is not None and p.slots[0].btype == "barracks"
        assert p.slots[3] is not None and p.slots[3].btype == "cannon"
        types = sorted(u.utype for u in p.units)
        assert types == ["dog", "dog", "robot"]
    assert [n.pos for n in game.state.nodes] == [(8, 2), (8, 8)]
    assert all(n.owner == -1 for n in game.state.nodes)
    assert game.state.tick == 0 and game.state.phase == "build"


def test_resource_cap_discards_overflow():
    game = create_game(seed=21)
    game.state.players[0].resources = 290
    skip_to(game, 1, "build")  # 进入第二轮构建（收入已发放）
    assert game.state.players[0].resources == 300  # 290+60 → 封顶


def test_action_ids_stable():
    """动作编号固定后含义不得静默改变（规则升级兼容性）。"""
    from thuai10.core.actions import decode

    assert decode(0, cfg).kind == "wait"
    assert decode(1, cfg).kind == "build" and decode(1, cfg).btype == "barracks"
    assert decode(7, cfg).btype == "cannon" and decode(7, cfg).slot == 0
    assert decode(13, cfg).btype == "shield"
    assert decode(19, cfg).kind == "tech"
    assert decode(20, cfg).utype == "dog"
    assert decode(22, cfg).utype == "siege"
    assert decode(23, cfg).kind == "layout"
    assert decode(38, cfg).kind == "repair" and decode(38, cfg).slot is None
    assert decode(44, cfg).slot == 5
    assert decode(45, cfg).utype == "dog" and decode(45, cfg).route == 0
    assert decode(53, cfg).utype == "siege" and decode(53, cfg).route == 2
    assert decode(54, cfg).kind == "signal" and decode(54, cfg).region == 0
    assert decode(71, cfg).kind == "bomb" and decode(71, cfg).region == 8
