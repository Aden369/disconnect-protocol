"""四方真实胜负、城墙与信号/导弹/屏蔽机制回归。"""

import copy

import numpy as np
from fastapi.testclient import TestClient

from thuai10.fourway.env import SHAPES, FourWayEnv
from thuai10.fourway.game import SIDES, UNIT_TYPES, FourWayGame, verify_replay
from thuai10.fourway.session import create
from thuai10.server.app import app


def remove_armies(game):
    game.entities = [e for e in game.entities if e.type not in UNIT_TYPES]
    game.compute_network()


def test_four_initial_companies_have_real_walls_and_units():
    game = FourWayGame()
    assert len(game.players) == 4
    for i in range(4):
        walls = [e for e in game.structures(i) if e.type == "wall"]
        assert len(walls) == 32 and sum(e.gate for e in walls) == 2
        assert len(game.units(i)) == 4
        assert len({e.slot for e in game.units(i)}) == 4
    assert all(len(m) == 41 and m[0] for m in game.legal_masks().values())


def test_money_and_relays_never_override_core_elimination():
    game = FourWayGame()
    remove_armies(game)
    game.players[0].resources = 300
    game.players[1].resources = 0
    for n in game.nodes:
        n["owner"] = 0
    game.headquarters(0).hp = 1
    game.headquarters(1).hp = 100
    game.headquarters(2).hp = 0
    game.headquarters(3).hp = 0
    game.tick = game.cfg["time"]["overload_tick"] - 1
    game.resolve_tick()
    assert game.winner == 1 and game.players[0].eliminated_tick == game.tick
    assert game.end_reason == "last_survivor"


def test_hard_limit_is_draw_even_with_different_health_or_money():
    game = FourWayGame()
    remove_armies(game)
    game.cfg["time"]["overload_tick"] = 1000
    game.players[0].resources = 300
    game.headquarters(0).hp = 1
    game.tick = game.cfg["time"]["max_ticks"] - 1
    game.resolve_tick()
    assert game.over and game.winner == -1 and game.end_reason == "time_limit_draw"


def test_all_four_attack_simultaneously_and_dead_attackers_fire():
    game = FourWayGame()
    game.entities = [e for e in game.entities if e.type == "hq"]
    game.cfg["units"]["robot"]["damage"] = 100
    for i in range(4):
        unit = game.produce_unit(i, "robot")
        unit.x, unit.y, unit.hp = 10, 10, 1
    game.resolve_tick()
    assert not any(game.units(i) for i in range(4))
    assert sum(a["kind"] == "attack" for a in game.activity) == 4


def test_wall_blocks_ground_and_line_of_fire_but_gate_authorizes_owner():
    game = FourWayGame()
    enemy = game.units(1)[2]
    friend = game.units(0)[2]
    enemy.x, enemy.y = friend.x, friend.y = 9, 4
    assert not game.shot_clear(enemy, game.headquarters(0))
    assert game.next_step(enemy, (4, 4), {}) is None
    assert game.next_step(friend, (4, 4), {}) == (8, 4)
    wall = next(
        e
        for e in game.entities
        if e.type == "wall" and e.player == 0 and e.pos == (8, 4)
    )
    wall.hp = 0
    assert game.next_step(enemy, (4, 4), {}) == (8, 4)


def test_air_unit_can_cross_wall_and_fire_over_it():
    game = FourWayGame()
    drone = next(e for e in game.units(1) if e.type == "drone")
    drone.x, drone.y = 9, 4
    assert game.next_step(drone, (4, 4), {}) == (8, 4)
    assert game.shot_clear(drone, game.headquarters(0))


def test_guided_missile_requires_beacon_and_enemy_jam_reduces_damage():
    game = FourWayGame()
    assert not any(game.mask(0)[23:32])
    game.step([16, 0, 0, 0])  # signal to NE base
    remove_armies(game)
    assert game.mask(0)[25]
    launch = game.step([25, 34, 0, 0])  # P1 jams its own NE core
    assert any(e["type"] == "lock_lost" for e in launch["events"])
    out = game.step([0, 0, 0, 0])
    impact = next(e for e in out["events"] if e["type"] == "missile_impact")
    assert impact["damage"] == 15 and not impact["locked"]
    assert game.headquarters(1).hp == 485
    assert game.headquarters(0).hp == 500


def test_unjammed_missile_does_full_damage():
    game = FourWayGame()
    game.step([16, 0, 0, 0])
    remove_armies(game)
    game.step([25, 0, 0, 0])
    out = game.step([0, 0, 0, 0])
    hit = next(e for e in out["events"] if e["type"] == "missile_impact")
    assert hit["locked"] and hit["damage"] == 75
    assert game.headquarters(1).hp == 425


def test_last_survivor_waits_for_eliminated_opponents_inflight_missile():
    game = FourWayGame()
    game.step([16, 0, 0, 0])
    remove_armies(game)
    game.step([25, 0, 0, 0])
    for i in (0, 2, 3):
        game.headquarters(i).hp = 0
    game.headquarters(1).hp = 10
    out = game.step([0, 0, 0, 0])
    assert not out["frames"][0]["done"]
    assert game.winner == -1 and game.end_reason == "mutual_destruction"


def test_offline_unit_keeps_uploaded_order_without_boundary_oscillation():
    game = FourWayGame()
    game.step([18, 0, 0, 0])  # center signal
    robot = next(e for e in game.units(0) if e.type == "robot")
    assert robot.command_goal == (14, 14)
    game.entities = [
        e for e in game.entities if not (e.player == 0 and e.type == "drone")
    ]
    robot.x, robot.y = 15, 4
    for n in game.nodes:
        n["owner"] = -1
    game.compute_network()
    assert robot.uid not in game.connected
    assert game.movement_goal(robot)[0] == (14, 14)
    game.clouds.append(
        {"uid": 999, "player": 1, "center": robot.pos, "until": game.tick + 20}
    )
    game.compute_network()
    game.receive_commands()
    assert game.movement_goal(robot)[0] != (14, 14)
    game.clouds = []
    game.compute_network()
    game.receive_commands()
    assert robot.command_until == 0  # same canceled beacon is not accepted repeatedly


def test_relay_extends_command_network_and_jam_disconnects_it():
    game = FourWayGame()
    game.nodes[0]["owner"] = 0
    robot = next(e for e in game.units(0) if e.type == "robot")
    robot.x, robot.y = 14, 10
    game.compute_network()
    assert robot.uid in game.connected and game.network_links
    game.clouds.append({"uid": 999, "player": 1, "center": (10, 10), "until": 20})
    game.compute_network()
    assert robot.uid not in game.connected
    assert 0 not in game.connected_relays[0]


def test_elimination_removes_army_walls_and_releases_relays():
    game = FourWayGame()
    game.nodes[0]["owner"] = 0
    game.headquarters(0).hp = 0
    game.resolve_tick()
    assert not game.units(0)
    assert all(e.type == "hq" for e in game.entities if e.player == 0)
    assert game.nodes[0]["owner"] == -1
    assert game.mask(0) == [True] + [False] * 40


def test_four_replay_is_deterministic_and_tampering_detected():
    _, session = create(10)
    for _ in range(12):
        session.step()
    replay = session.game.replay()
    assert verify_replay(replay)["ok"]
    bad = copy.deepcopy(replay)
    bad["actions"][0][0] = 0
    assert not verify_replay(bad)["ok"]


def test_four_environment_shapes_and_all_agents_are_explicit():
    env = FourWayEnv()
    obs, info = env.reset()
    assert set(obs) == set(SIDES)
    for side in SIDES:
        for key, shape in SHAPES.items():
            assert obs[side][key].shape == shape
            assert np.all(np.isfinite(obs[side][key]))
    obs, rewards, _term, trunc, info = env.step(dict.fromkeys(SIDES, 0))
    assert set(rewards) == set(SIDES)
    assert all(info["mask"][side][0] for side in SIDES)
    assert not any(trunc.values())


def test_each_four_policy_called_once_with_same_old_tick():
    class Counting:
        def __init__(self):
            self.ticks = []

        def act(self, game, player):
            self.ticks.append(game.tick)
            return 0

    _, session = create()
    session.bots = [Counting() for _ in range(4)]
    session.step()
    assert all(b.ticks == [0] for b in session.bots)


def test_electronic_policy_interdicts_a_rivals_guided_missile():
    from thuai10.fourway.policies import Policy

    game = FourWayGame()
    game.step([16, 0, 0, 0])
    game.step([25, 0, 0, 0])
    assert Policy("electronic").act(game, 2) == 34


def test_rotating_policy_lineup_preserves_outcome_and_core_health():
    names = ["breach", "missile", "electronic", "fortress"]
    _, a = create(10, names)
    _, b = create(10, [names[-1], *names[:-1]])
    while not a.game.over:
        a.step()
    while not b.game.over:
        b.step()
    assert a.game.tick == b.game.tick
    assert (
        b.game.winner == (a.game.winner + 1) % 4
        if a.game.winner >= 0
        else b.game.winner == -1
    )
    assert [b.game.headquarters((i + 1) % 4).hp for i in range(4)] == [
        a.game.headquarters(i).hp for i in range(4)
    ]


def test_default_http_game_is_four_sided_with_skill_frames():
    client = TestClient(app)
    created = client.post("/api/games", json={}).json()
    assert len(created["frame"]["players"]) == 4
    assert len(created["frame"]["walls"]) == 128
    assert set(created["masks"]) == set(SIDES)
    sid = created["game_id"]
    out = client.post(f"/api/games/{sid}/step", json={}).json()
    assert len(out["decisions"]) == 4 and len(out["frames"]) == 4
    assert (
        client.get(f"/api/games/{sid}/replay").json()["rules_version"]
        == "game-rules-v0.5"
    )


def test_drone_cap_cost_and_ground_capture_only():
    game = FourWayGame()
    assert game.cfg["units"]["drone"]["cost"] == 45
    game.players[0].resources = 300
    assert game.mask(0)[4]
    game.produce_unit(0, "drone")
    assert not game.mask(0)[4]
    remove_armies(game)
    drone = game.spawn(0, "drone", (10, 10), slot=0)
    drone.command_goal = (10, 10)
    drone.command_until = 100
    for _ in range(5):
        game.resolve_tick()
    assert game.nodes[0]["owner"] == -1
    dog = game.spawn(0, "dog", (10, 10), slot=1)
    dog.objective = (10, 10)
    for _ in range(4):
        game.resolve_tick()
    assert game.nodes[0]["owner"] == 0


def test_drone_never_attacks_even_after_tech_upgrade():
    game = FourWayGame()
    remove_armies(game)
    drone = game.spawn(0, "drone", game.headquarters(1).pos, slot=0)
    game.players[0].tech = 1
    drone.command_goal = drone.pos
    drone.command_until = 100
    initial = game.headquarters(1).hp
    game.resolve_tick()
    assert game.headquarters(1).hp == initial
    assert not any(
        a["uid"] == drone.uid and a["kind"] == "attack" for a in game.activity
    )


def test_ground_specialists_cannot_shoot_air_but_mech_can_over_wall():
    for kind, armed in (
        ("dog", False),
        ("siege", False),
        ("robot", True),
        ("cannon", True),
    ):
        game = FourWayGame()
        game.entities = [e for e in game.entities if e.type == "hq"]
        attacker = game.spawn(0, kind, (10, 11) if kind == "dog" else (9, 10), slot=0)
        game.spawn(1, "wall", (10, 10))
        drone = game.spawn(1, "drone", (11, 10), slot=0)
        drone.command_goal = drone.pos
        drone.command_until = 100
        game.resolve_tick()
        shots = [
            a
            for a in game.activity
            if a["uid"] == attacker.uid
            and a.get("target_uid") == drone.uid
            and a["kind"] == "attack"
        ]
        assert bool(shots) == armed
        assert (drone.hp < drone.max_hp) == armed


def test_support_drone_follows_ground_and_retreats_when_jammed():
    game = FourWayGame()
    drone = next(e for e in game.units(0) if e.type == "drone")
    robot = next(e for e in game.units(0) if e.type == "robot")
    robot.x, robot.y = 8, 8
    assert game.movement_goal(drone) == (robot.pos, "通信接力：跟随robot")
    game.clouds.append({"uid": 1000, "player": 1, "center": drone.pos, "until": 100})
    assert game.movement_goal(drone) == (game.headquarters(0).pos, "受屏蔽，返回总部")


def test_historical_v03_fourway_replay_still_verifies():
    import json
    from pathlib import Path

    from thuai10.core.replay import verify

    replay = json.loads(
        Path("results/fourway-replay-v0.3.json").read_text(encoding="utf-8")
    )
    assert verify(replay)["ok"]


def test_larger_bases_are_rotated_disjoint_and_defenses_inside_walls():
    game = FourWayGame()
    assert game.cfg["map"]["size"] == 29
    occupied = set()
    for player in range(4):
        structures = game.structures(player)
        positions = {e.pos for e in structures}
        assert len(positions) == len(structures)
        assert not positions & occupied
        occupied |= positions
        assert game.headquarters(player).pos == game.world((4, 4), player)
        assert {e.type for e in structures} == {
            "hq",
            "wall",
            "cannon",
            "mortar",
            "antiair",
            "jammer",
        }
        for e in structures:
            x, y = game.local(e.pos, player)
            assert 0 <= x <= 8 and 0 <= y <= 8
            if e.type != "wall":
                assert 0 < x < 8 and 0 < y < 8
        for unit in game.units(player):
            assert unit.pos not in occupied
        assert all(
            e.objective == game.headquarters((player + 1) % 4).pos
            for e in game.units(player)
            if e.type == "robot"
        )


def test_mortar_splash_is_ground_only_enemy_only_and_has_cooldown():
    game = FourWayGame()
    game.entities = [e for e in game.entities if e.type == "hq"]
    gun = game.spawn(0, "mortar", (10, 14))
    game.spawn(1, "wall", (11, 14))
    targets = [
        game.spawn(1, "robot", (12, 14), slot=0),
        game.spawn(2, "robot", (12, 15), slot=0),
    ]
    friend = game.spawn(0, "robot", (12, 14), slot=0)
    drone = game.spawn(1, "drone", (12, 14), slot=1)
    for unit in [*targets, friend, drone]:
        unit.last_attack = 100
        unit.last_move = 100
    game.resolve_tick()
    assert all(e.hp == e.max_hp - 12 for e in targets)
    assert friend.hp == friend.max_hp and drone.hp == drone.max_hp
    assert next(a for a in game.activity if a["uid"] == gun.uid)["kind"] == "attack"
    game.resolve_tick()
    assert all(e.hp == e.max_hp - 12 for e in targets)


def test_air_defense_ignores_ground_and_shoots_drone_over_wall():
    game = FourWayGame()
    game.entities = [e for e in game.entities if e.type == "hq"]
    gun = game.spawn(0, "antiair", (10, 14))
    ground = game.spawn(1, "robot", (11, 14), slot=0)
    drone = game.spawn(1, "drone", (13, 14), slot=1)
    game.spawn(1, "wall", (12, 14))
    ground.last_attack = ground.last_move = drone.last_move = 100
    game.resolve_tick()
    assert ground.hp == ground.max_hp
    assert drone.hp == drone.max_hp - 15
    assert (
        next(a for a in game.activity if a["uid"] == gun.uid)["target_uid"] == drone.uid
    )


def test_new_defenses_and_extra_walls_are_in_fixed_observation_slots():
    from thuai10.fourway.env import observe

    game = FourWayGame()
    obs = observe(game, 0)
    assert obs["structures"].shape == (4, 38, 10)
    assert all(obs["structures"][i, :, 0].sum() == 37 for i in range(4))
    game.players[0].resources = 100
    assert game.mask(0)[5]
    game.execute(0, 5)
    obs = observe(game, 0)
    assert obs["structures"][0, :, 0].sum() == 38


def test_v04_replay_compatibility_after_map_expansion():
    import json
    from pathlib import Path

    replay = json.loads(
        Path("results/fourway-replay-v0.4.json").read_text(encoding="utf-8")
    )
    assert verify_replay(replay)["ok"]


def test_hq_jam_disconnects_remote_relay_but_existing_beacon_stays_active():
    game = FourWayGame()
    game.execute(0, 16)
    beacon = game.beacons[0]
    game.nodes[0]["owner"] = 0
    robot = next(e for e in game.units(0) if e.type == "robot")
    robot.x, robot.y = 10, 10
    game.compute_network()
    assert robot.uid in game.connected
    game.clouds.append(
        {"uid": 9999, "player": 1, "center": game.headquarters(0).pos, "until": 20}
    )
    assert not game.jammed(robot.pos, 0)
    game.compute_network()
    assert not game.connected_relays[0]
    assert not any(e.uid in game.connected for e in game.units(0))
    assert game.beacon_active(beacon)
    assert game.mask(0)[
        25
    ]  # Existing lock permits missile despite source network loss.
    assert not game.mask(0)[14]


def test_two_support_drones_share_only_ground_escort():
    game = FourWayGame()
    game.entities = [e for e in game.entities if e.type not in UNIT_TYPES]
    robot = game.spawn(0, "robot", (10, 10), slot=0)
    drones = [
        game.spawn(0, "drone", (9, 10), slot=1),
        game.spawn(0, "drone", (8, 10), slot=2),
    ]
    assert all(game.movement_goal(drone)[0] == robot.pos for drone in drones)


def test_missile_launch_allowed_at_176_seconds_but_not_178():
    game = FourWayGame()
    game.tick = 352
    game.execute(0, 14)
    assert game.mask(0)[23]
    game.tick = 356
    assert not game.mask(0)[23]


def test_technology_applies_to_all_defensive_guns_but_not_structure_damage():
    game = FourWayGame()
    game.entities = [e for e in game.entities if e.type == "hq"]
    game.players[0].tech = 1
    cannon = game.spawn(0, "cannon", (10, 10))
    mortar = game.spawn(0, "mortar", (10, 11))
    antiair = game.spawn(0, "antiair", (10, 12))
    target = game.spawn(1, "robot", (12, 10), slot=0)
    drone = game.spawn(1, "drone", (10, 14), slot=1)
    target.last_attack = target.last_move = drone.last_move = 100
    game.resolve_tick()
    activity = {a["uid"]: a for a in game.activity}
    assert activity[cannon.uid]["damage"] == 22
    assert activity[mortar.uid]["damage"] == 16
    assert activity[antiair.uid]["damage"] == 19
    game.entities = [e for e in game.entities if e.type == "hq"]
    siege = game.spawn(0, "siege", (10, 10), slot=0)
    wall = game.spawn(1, "wall", (12, 10))
    game.resolve_tick()
    assert wall.hp == 62
    assert next(a for a in game.activity if a["uid"] == siege.uid)["damage"] == 38


def test_ground_skill_experiment_damage_disruption_and_escape():
    import runpy

    run = runpy.run_path("scripts/experiment_ground_skills.py")["run"]
    cases = {row["case"]: row for row in run()["cases"]}
    assert cases["control"]["ground_damage"] == 0
    assert cases["missile"]["ground_damage"] == 215
    assert cases["missile"]["missile_ground_hits"] == 3
    assert cases["missile"]["ground_kills"] == 1
    assert cases["emp"]["ground_damage"] == 0
    assert cases["emp"]["linked_before"] == 3
    assert cases["emp"]["linked_after"] == cases["emp"]["commanded_after"] == 0
    assert cases["moving_missile"]["missile_ground_hits"] < 3


def test_policies_use_ground_signal_missile_and_frontline_emp():
    import runpy

    from thuai10.fourway.policies import Policy

    game, _ = runpy.run_path("scripts/experiment_ground_skills.py")["setup"]()
    missile = Policy("missile")
    assert missile.act(game, 0) == 18  # Signal the central ground cluster.
    game.execute(0, 18)
    assert missile.act(game, 0) == 27  # Launch at that signal instead of an HQ.
    electronic = Policy("electronic")
    assert electronic.act(game, 0) == 36
    assert "地面" in electronic.last_reason


def test_policy_does_not_replace_beacon_while_own_missile_is_in_flight():
    import runpy

    from thuai10.fourway.policies import Policy

    game, _ = runpy.run_path("scripts/experiment_ground_skills.py")["setup"]()
    game.execute(0, 16)  # Establish a separate HQ strike.
    game.tick = 4
    game.execute(0, 25)
    game.tick = 8
    assert game.mask(0)[18]
    assert Policy("missile").act(game, 0) not in range(14, 23)
