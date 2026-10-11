"""M2 验收：路径、冷却、同步伤害、护盾、节点、轰炸、撤军和胜负。小场景验证具体数值。"""
from __future__ import annotations

from thuai10.core import create_game
from thuai10.core.combat import reduce_damage, shield_of
from thuai10.core.config import load_config
from thuai10.core.model import Building, Unit
from thuai10.core.pathing import best_endpoint, next_step

cfg = load_config()


# ---- 测试工具 ------------------------------------------------------------


def to_attack(game, round_no: int = 0):
    while not game.state.over and not (
        game.state.round == round_no and game.state.phase == "attack"
    ):
        game.step([0, 0])


def add_unit(game, player, utype, pos, hp=None):
    p = game.state.players[player]
    used = [u.local_id for u in p.units] + [b.local_id for b in p.buildings()]
    u = Unit(
        uid=game.state.alloc_uid(),
        local_id=(max(used) + 1) if used else 0,
        owner=player,
        utype=utype,
        hp=hp if hp is not None else cfg.units[utype]["hp"],
        birth_tick=game.state.tick,
        on_field=True,
        pos=pos,
    )
    p.units.append(u)
    return u


def add_building(game, player, btype, pos, hp=None):
    p = game.state.players[player]
    used = [u.local_id for u in p.units] + [b.local_id for b in p.buildings()]
    b = Building(
        uid=game.state.alloc_uid(),
        local_id=(max(used) + 1) if used else 0,
        owner=player,
        btype=btype,
        hp=hp if hp is not None else cfg.buildings[btype]["hp"],
        max_hp=cfg.buildings[btype]["hp"],
        slot=None,
        pos=pos,
    )
    # 挂到空槽位上以参与 targeting / 摧毁结算（槽位仅作容器）
    for i in range(6):
        if p.slots[i] is None:
            b.slot = i
            p.slots[i] = b
            break
    return b


def strip_to_duel(game):
    """清空双方建筑与单位，只留总部（便于构造小场景）。"""
    for p in game.state.players:
        p.units.clear()
        for i in range(6):
            p.slots[i] = None


# ---- 路径 ----------------------------------------------------------------


def test_path_prefers_front_then_north_south_back():
    walkable = {(x, y) for x in range(17) for y in range(11)}
    # p0 本地前=+x：先向前走
    step = next_step((4, 5), (8, 2), walkable, cfg, 0)
    assert step == (5, 5)
    # p1 镜像：前=-x
    step = next_step((12, 5), (8, 2), walkable, cfg, 1)
    assert step == (11, 5)


def test_path_blocked_by_buildings_and_detours():
    walkable = {(x, y) for x in range(17) for y in range(11)}
    # 目标可走则直接到达
    assert best_endpoint((4, 5), (8, 2), walkable, cfg, 0) == (8, 2)
    # 目标不可走（建筑）：到达相邻最优格
    walkable.discard((8, 2))
    ep = best_endpoint((4, 5), (8, 2), walkable, cfg, 0)
    assert abs(ep[0] - 8) + abs(ep[1] - 2) == 1


def test_path_mirror_consistent():
    walkable = {(x, y) for x in range(17) for y in range(11)}
    for start, target in [((4, 5), (8, 2)), ((2, 8), (14, 2)), ((4, 2), (15, 5))]:
        s0 = next_step(start, target, walkable, cfg, 0)
        mir = lambda xy: (16 - xy[0], xy[1])
        s1 = next_step(mir(start), mir(target), walkable, cfg, 1)
        assert s1 == mir(s0), (start, target, s0, s1)


# ---- 攻击与冷却 ----------------------------------------------------------


def test_dog_attacks_every_two_ticks():
    game = create_game(seed=100)
    to_attack(game)
    strip_to_duel(game)
    dog = add_unit(game, 0, "dog", (8, 5))
    target = add_building(game, 1, "barracks", (9, 5))
    game.step([0, 0])  # e=0..4：狗应攻击 tick 21,23 → 2 次
    assert target.hp == 180 - 20
    game.step([0, 0])  # tick 25,27 → 2 次
    assert target.hp == 180 - 40


def test_simultaneous_damage_both_deal():
    game = create_game(seed=101)
    to_attack(game)
    strip_to_duel(game)
    a = add_unit(game, 0, "dog", (8, 5), hp=10)
    b = add_unit(game, 1, "dog", (9, 5), hp=40)
    game.step([0, 0])
    # 同步结算：a 即使本 tick 阵亡仍打出 10 伤害
    assert a.hp <= 0
    assert b.hp == 30


def test_dead_unit_still_completes_selected_attack():
    game = create_game(seed=102)
    to_attack(game)
    strip_to_duel(game)
    a = add_unit(game, 0, "dog", (8, 5), hp=1)
    b = add_unit(game, 1, "robot", (9, 5), hp=100)  # 机器人对狗一击 15
    game.step([0, 0])
    assert a.hp <= 0          # 被 b 击杀
    assert b.hp == 100 - 10   # a 的攻击仍然生效


def test_cannon_stats_and_cooldown():
    game = create_game(seed=103)
    to_attack(game)
    strip_to_duel(game)
    add_building(game, 0, "cannon", (5, 2))
    u = add_unit(game, 1, "dog", (9, 2), hp=60)  # 距离 4
    game.step([0, 0])  # tick 21,23
    assert u.hp == 60 - 32  # 16×2
    # 对建筑无效：只有建筑在射程内时不开火
    game2 = create_game(seed=103)
    to_attack(game2)
    strip_to_duel(game2)
    add_building(game2, 0, "cannon", (5, 2))
    b = add_building(game2, 1, "barracks", (9, 2))
    game2.step([0, 0])
    assert b.hp == 180


def test_cannon_tech1_damage():
    game = create_game(seed=104)
    game.state.players[0].tech = 1
    to_attack(game)
    strip_to_duel(game)
    add_building(game, 0, "cannon", (5, 2))
    u = add_unit(game, 1, "dog", (9, 2), hp=60)
    game.step([0, 0])
    assert u.hp == 60 - 40  # 20×2


def test_siege_prefers_buildings_and_split_damage():
    game = create_game(seed=105)
    game.state.players[0].tech = 1
    to_attack(game)
    strip_to_duel(game)
    s = add_unit(game, 0, "siege", (8, 5))
    add_unit(game, 1, "dog", (10, 5), hp=60)      # 单位，距离 2
    b = add_building(game, 1, "barracks", (11, 5))  # 建筑，距离 3
    game.step([0, 0])  # 攻城冷却 4 tick：本块只攻击一次（tick 21）
    assert b.hp == 180 - 35, "攻城车优先建筑，对建筑 35"
    game2 = create_game(seed=105)
    game2.state.players[0].tech = 1
    to_attack(game2)
    strip_to_duel(game2)
    add_unit(game2, 0, "siege", (8, 5))
    u = add_unit(game2, 1, "dog", (10, 5), hp=60)
    game2.step([0, 0])
    assert u.hp == 60 - 8, "攻城车对单位仅 8"


# ---- 护盾 ----------------------------------------------------------------


def test_shield_reduces_per_source_min_one():
    game = create_game(seed=106)
    to_attack(game)
    strip_to_duel(game)
    shield = add_building(game, 0, "shield", (2, 5))
    hq = game.state.players[0].hq
    assert shield_of(hq, game.state, cfg) is shield
    assert reduce_damage(10, hq, game.state, cfg) == 2
    assert reduce_damage(8, hq, game.state, cfg) == 1, "最低为 1"
    assert reduce_damage(5, hq, game.state, cfg) == 1, "最低为 1"
    # 不保护单位
    u = add_unit(game, 0, "dog", (2, 4))
    assert reduce_damage(10, u, game.state, cfg) == 10
    # 不保护自身
    assert reduce_damage(10, shield, game.state, cfg) == 10
    # 距离 >2 不保护
    far = add_building(game, 0, "barracks", (2, 8))
    assert shield_of(far, game.state, cfg) is None


def test_shield_applies_all_tick_damage_even_if_destroyed():
    """护盾塔本 tick 开始时存活即对该 tick 所有伤害减伤。"""
    game = create_game(seed=107)
    to_attack(game)
    strip_to_duel(game)
    shield = add_building(game, 0, "shield", (2, 5), hp=1)
    hq = game.state.players[0].hq
    hq.hp = 100
    # p1 双狗近战总部与护盾塔：同 tick 内先打掉护盾再打总部
    add_unit(game, 1, "dog", (1, 4), hp=60)   # 距 HQ 1、距护盾 2
    add_unit(game, 1, "dog", (3, 5), hp=60)   # 距护盾 1、距 HQ 2
    out = game.step([0, 0])
    frame0 = out["frames"][0]
    hq_hp_t21 = [b for b in frame0["buildings"] if b["type"] == "hq" and b["player"] == 0][0]["hp"]
    assert hq_hp_t21 == 100 - 2, "护盾塔同 tick 被打掉时，该 tick 总部伤害仍减免（10-8=2）"


# ---- 节点 ----------------------------------------------------------------


def test_capture_needs_four_ticks_exclusive():
    game = create_game(seed=108)
    to_attack(game)
    strip_to_duel(game)
    add_unit(game, 0, "dog", (8, 2))
    node = game.state.nodes[0]
    out = game.step([0, 0])
    frames = out["frames"]
    prog = [f["nodes"][0]["progress"] for f in frames]
    own = [f["nodes"][0]["owner"] for f in frames]
    assert prog == [1, 2, 3, 0], "连续 4 tick 占领进度递增"
    assert own[:3] == [-1, -1, -1] and own[3] == 0, "第 4 tick 取得控制"


def test_contested_resets_progress():
    game = create_game(seed=109)
    to_attack(game)
    strip_to_duel(game)
    add_unit(game, 0, "dog", (8, 2))
    add_unit(game, 1, "dog", (8, 3))  # 争夺：双方在占领范围内
    node = game.state.nodes[0]
    node.progress = 2
    node.progress_player = 0
    game.step([0, 0])
    assert node.progress == 0
    assert node.owner == -1, "争夺清零进度且不改变归属"

def test_capture_completes_after_four_ticks():
    game = create_game(seed=1092)
    to_attack(game)
    strip_to_duel(game)
    add_unit(game, 0, "dog", (8, 2))
    node = game.state.nodes[0]
    game.step([0, 0])  # 4 tick：完成占领
    assert node.owner == 0


def test_dead_units_cannot_capture():
    game = create_game(seed=110)
    to_attack(game)
    strip_to_duel(game)
    node = game.state.nodes[0]
    node.progress = 3
    node.progress_player = 0
    add_unit(game, 0, "dog", (8, 2), hp=1)
    add_building(game, 1, "cannon", (5, 2))  # 一击 16 杀狗
    game.step([0, 0])
    assert node.owner == -1, "本 tick 被杀的单位不能占领"
    assert node.progress == 0


def test_owner_scores_while_contested_and_control_seconds():
    game = create_game(seed=111)
    to_attack(game)
    strip_to_duel(game)
    node = game.state.nodes[0]
    node.owner = 0
    add_unit(game, 0, "dog", (7, 2))   # 己方也在场 → 争夺，无法被夺取
    add_unit(game, 1, "dog", (8, 3))   # 敌军进入：原控制方仍积分
    game.step([0, 0])
    assert node.owner == 0
    assert game.state.players[0].control_ticks == 4, "每 tick 0.5 控制秒 ×4 tick"
    assert game.state.players[0].control_ticks * 0.5 == 2.0

def test_owner_scores_until_capture_completes():
    game = create_game(seed=1112)
    to_attack(game)
    strip_to_duel(game)
    node = game.state.nodes[0]
    node.owner = 0
    add_unit(game, 1, "dog", (8, 2))  # 仅敌军在场 → 夺取中
    game.step([0, 0])  # tick 21-24：第 4 tick 被夺取
    assert node.owner == 1
    assert game.state.players[0].control_ticks == 3
    assert game.state.players[1].control_ticks == 1


# ---- 轰炸与信号 ----------------------------------------------------------


def test_bomb_lands_at_e_plus_4_last_at_40():
    game = create_game(seed=112)
    to_attack(game)
    strip_to_duel(game)
    hq1 = game.state.players[1].hq
    hq1.hp = 10
    game.state.players[0].resources = 300
    out = None
    for i in range(9):
        game.step([0, 0])
    out = game.step([63 + 5, 0])  # e=36 决策轰炸本地 (14,5) → 世界 (14,5) 近 p1 总部
    bombs = [e for e in out["events"] if e["type"] == "bomb"]
    assert bombs, "最后一次轰炸应在最后一 tick 落下"
    assert bombs[0]["tick"] == 60, "第 40 进攻 tick（绝对 tick 60）落下"
    assert game.state.over and game.state.winner == 0


def test_bomb_damage_radius_and_no_friendly_fire():
    game = create_game(seed=113)
    to_attack(game)
    strip_to_duel(game)
    game.state.players[0].resources = 300
    p0b = add_building(game, 0, "barracks", (2, 5))
    e1 = add_building(game, 1, "barracks", (2, 4))   # 距 (2,5) 1 → 命中
    e2 = add_building(game, 1, "barracks", (2, 6))   # 距 1 → 命中
    e3 = add_building(game, 1, "barracks", (2, 7))   # 距 2 → 免疫
    game.step([63 + 3, 0])  # 本地 (2,5) 世界 (2,5)，e+4 落下
    assert e1.hp == 180 - 30 and e2.hp == 180 - 30 and e3.hp == 180
    assert p0b.hp == 180, "轰炸不伤己方"
    assert game.state.players[0].bomb_used


def test_bomb_tech1_damage():
    game = create_game(seed=114)
    game.state.players[0].tech = 1
    to_attack(game)
    strip_to_duel(game)
    game.state.players[0].resources = 300
    e1 = add_building(game, 1, "barracks", (2, 5))
    game.step([63 + 3, 0])
    assert e1.hp == 180 - 40


def test_signal_redirects_movement():
    game = create_game(seed=115)
    to_attack(game)
    strip_to_duel(game)
    game.state.players[0].resources = 300
    dog = add_unit(game, 0, "dog", (8, 5))
    game.step([54 + 2, 0])  # 信号本地 (14,2) → 世界 (14,2)
    # 4 tick 后狗应朝 (14,2) 方向移动（向东）
    assert dog.pos[0] > 8
    assert game.state.players[0].signal_center == (14, 2)


def test_signal_expires_after_16_ticks():
    game = create_game(seed=116)
    to_attack(game)
    strip_to_duel(game)
    game.state.players[0].resources = 300
    dog = add_unit(game, 0, "dog", (4, 5))
    game.step([54 + 2, 0])  # e=0 决策：有效至 e=16
    for _ in range(3):
        game.step([0, 0])  # e=4,8,12
    assert game.state.players[0].signal_center is not None
    game.step([0, 0])  # e=13..16：完成 e=16 后失效
    assert game.state.players[0].signal_center is None
    # 失效后默认目标：最近非己方节点 (8,2)（北）
    assert dog.pos[1] <= 5


# ---- 撤军、镜像与胜负 ----------------------------------------------------


def test_retreat_returns_units_with_ready_cooldowns():
    game = create_game(seed=117)
    to_attack(game)
    strip_to_duel(game)
    dog = add_unit(game, 0, "dog", (8, 5), hp=42)
    add_building(game, 1, "barracks", (9, 5))
    for _ in range(10):
        game.step([0, 0])
    assert not dog.on_field and dog.pos is None
    assert dog.last_move_tick <= -10**9 and dog.last_attack_tick <= -10**9
    assert game.state.players[0].deploy_used == 0
    assert game.state.players[0].signal_center is None


def test_retreat_preserves_wounded_unit_hp():
    game = create_game(seed=118)
    to_attack(game)
    strip_to_duel(game)
    dog = add_unit(game, 0, "dog", (8, 5), hp=100)
    dog.hp = 33
    for _ in range(10):
        game.step([0, 0])
    assert dog in game.state.players[0].units
    assert not dog.on_field
    assert dog.hp == 33, "撤军保留单位 HP"


def test_hq_destroyed_wins():
    game = create_game(seed=119)
    to_attack(game)
    strip_to_duel(game)
    game.state.players[1].hq.hp = 5
    add_unit(game, 0, "dog", (14, 5))  # 距敌总部 1
    game.step([0, 0])
    assert game.state.over
    assert game.state.winner == 0
    assert game.state.end_reason == "hq_destroyed"


def test_both_hqs_die_same_tick_is_draw():
    game = create_game(seed=120)
    to_attack(game)
    strip_to_duel(game)
    game.state.players[0].resources = 300
    game.state.players[1].resources = 300
    game.state.players[0].hq.hp = 10
    game.state.players[1].hq.hp = 10
    # 双方同时轰炸敌方总部旁区域：p0 本地 (14,5)→世界(14,5) 近 p1 总部；
    # p1 本地 (14,5)→世界(2,5) 近 p0 总部。同 tick 落下。
    game.step([68, 68])
    assert game.state.over
    assert game.state.winner == -1
    assert game.state.end_reason == "hq_destroyed"


def test_mirror_consistency_swap_sides():
    """换边镜像一致：同一动作序列交换玩家后结果镜像。"""
    seq = [
        [20, 2],      # 双方生产/建造
        [19, 0],
        [0, 23 + 5],
        [0, 0],
        [45, 47],     # 部署
        [54 + 4, 63],
        [0, 45],
        [46, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [20, 0],
        [0, 0],
        [0, 0],
    ]
    ga, gb = create_game(seed=7), create_game(seed=7)
    for a0, a1 in seq:
        if ga.state.over:
            break
        ga.step([a0, a1])
        gb.step([a1, a0])
    sa, sb = ga.snapshot(), gb.snapshot()
    for k in ("resources", "tech", "control_ticks"):
        assert sa["players"][0][k] == sb["players"][1][k]
        assert sa["players"][1][k] == sb["players"][0][k]
    assert sa["players"][0]["hq"]["hp"] == sb["players"][1]["hq"]["hp"]
    assert [n["owner"] for n in sa["nodes"]] == [
        -1 if o == -1 else 1 - o for o in (n["owner"] for n in sb["nodes"])
    ]
    ua = sorted((u["type"], u["x"], u["y"], u["hp"], u["on_field"]) for u in sa["players"][0]["units"])
    ub = sorted((u["type"], u["x"], u["y"], u["hp"], u["on_field"]) for u in sb["players"][1]["units"])
    assert ua == ub, "本地坐标下双方单位状态镜像一致"


def test_walkable_after_destroy_next_tick():
    game = create_game(seed=121)
    to_attack(game)
    strip_to_duel(game)
    b = add_building(game, 1, "barracks", (8, 5), hp=5)
    dog = add_unit(game, 0, "dog", (8, 4))  # 射程 1 内，一击 10 拆掉 5 HP
    game.step([0, 0])  # tick 21 起攻击
    assert b.hp <= 0
    game.step([0, 0])
    # 路径应允许走到 (8,5)（被毁建筑格下 tick 起可走）
    from thuai10.core.combat import walkable_cells

    assert (8, 5) in walkable_cells(game.state, cfg)
