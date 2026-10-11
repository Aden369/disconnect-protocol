"""接口测试：创建对局、step、回放导出。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from thuai10.server.app import app

client = TestClient(app)


def test_create_and_step_human():
    r = client.post("/api/games", json={"mode": "human", "human_side": "left", "seed": 1})
    assert r.status_code == 200
    data = r.json()
    sid = data["game_id"]
    assert data["state"]["phase"] == "build"
    assert data["masks"]["left"][0] is True

    r = client.post(f"/api/games/{sid}/step", json={"action": 20})
    assert r.status_code == 200
    out = r.json()
    assert len(out["frames"]) == 10, "构建阶段推进 10 tick"
    assert out["state"]["phase"] == "layout"
    assert out["masks"]["left"][0] is True
    # 对手脚本读取旧观测：p1 生产/建筑动作已由脚本决定并统一结算
    assert out["state"]["steps_taken"] == 1


def test_watch_mode_two_bots():
    r = client.post("/api/games", json={"mode": "watch", "seed": 2,
                                        "bot_left": "node_grabber", "bot_right": "tech_siege"})
    sid = r.json()["game_id"]
    for _ in range(3):
        out = client.post(f"/api/games/{sid}/step", json={"action": None}).json()
        assert len(out["frames"]) > 0
    assert out["state"]["steps_taken"] == 3


def test_replay_export_and_verify():
    from thuai10.core.replay import verify

    r = client.post("/api/games", json={"mode": "watch", "seed": 3})
    sid = r.json()["game_id"]
    for _ in range(12):
        out = client.post(f"/api/games/{sid}/step", json={"action": None}).json()
        if out["done"]:
            break
    replay = client.get(f"/api/games/{sid}/replay").json()
    assert replay["schema_version"]
    assert replay["actions"]
    result = verify(replay)
    assert result["ok"], result


def test_reset_and_404():
    r = client.post("/api/games", json={"mode": "human", "seed": 4})
    sid = r.json()["game_id"]
    client.post(f"/api/games/{sid}/step", json={"action": 0})
    out = client.post(f"/api/games/{sid}/reset", json={}).json()
    assert out["state"]["tick"] == 0
    assert client.get("/api/games/nope").status_code == 404


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "断链协议" in r.text
