"""FastAPI 本地接口：创建对局、step、状态查询与回放导出。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from thuai10.bots import BOTS
from thuai10.fourway import session as four
from thuai10.fourway.policies import POLICIES

from .session import replay_of, step_session, store

WEB_DIR = Path(__file__).resolve().parents[3] / "web"

app = FastAPI(title="THUAI10 算力领土 demo", version="0.1")


class CreateGameReq(BaseModel):
    mode: str = Field("four", description="four 为四方新规则；human/watch 保留旧回放调试")
    human_side: str = Field("left", description="left / right")
    seed: int = 0
    bot_left: str = "node_grabber"
    bot_right: str = "tech_siege"
    policies: list[str] = Field(default_factory=lambda: ["breach", "missile", "electronic", "fortress"])


class StepReq(BaseModel):
    action: Optional[int] = None
    actions: Optional[dict[str, int]] = None


class ResetReq(BaseModel):
    seed: Optional[int] = None


def _sess_or_404(sid: str):
    try:
        return store.get(sid)
    except KeyError:
        raise HTTPException(404, "对局不存在")


@app.post("/api/games")
def create_game(req: CreateGameReq) -> dict:
    if req.mode == "four":
        if len(req.policies) != 4 or any(name not in POLICIES for name in req.policies):
            raise HTTPException(400, "四方各需要一个有效策略")
        sid, sess = four.create(req.seed, req.policies)
        return {"game_id": sid, "state": sess.game.snapshot(), "frame": sess.game.frame(),
                "masks": sess.game.legal_masks(), "config": sess.game.cfg, "policies": sess.names}
    if req.mode not in ("human", "watch"):
        raise HTTPException(400, "mode 应为 human 或 watch")
    if req.bot_left not in BOTS or req.bot_right not in BOTS:
        raise HTTPException(400, f"未知脚本，可选 {sorted(BOTS)}")
    sid, sess = store.create(
        mode=req.mode,
        human_side=req.human_side,
        seed=req.seed,
        bot_left=req.bot_left,
        bot_right=req.bot_right,
        meta={"mode": req.mode, "seed": req.seed},
    )
    return {
        "game_id": sid,
        "state": sess.game.snapshot(),
        "masks": sess.game.legal_masks(),
        "frame": sess.game._frame(),
        "config": sess.game.cfg.raw,
    }


@app.get("/api/games/{sid}")
def get_game(sid: str) -> dict:
    if sid in four.sessions:
        sess = four.sessions[sid]
        return {"game_id": sid, "state": sess.game.snapshot(), "frame": sess.game.frame(),
                "masks": sess.game.legal_masks(), "mode": "four", "policies": sess.names}
    sess = _sess_or_404(sid)
    return {
        "game_id": sid,
        "state": sess.game.snapshot(),
        "masks": sess.game.legal_masks(),
        "scores": sess.game.scores(),
        "mode": sess.mode,
        "human_side": sess.human_side,
    }


@app.post("/api/games/{sid}/step")
def step_game(sid: str, req: StepReq) -> dict:
    if sid in four.sessions:
        sess = four.sessions[sid]
        if sess.game.over:
            raise HTTPException(400, "对局已结束")
        return sess.step(req.actions)
    sess = _sess_or_404(sid)
    if sess.game.state.over:
        raise HTTPException(400, "对局已结束")
    out = step_session(sess, req.action)
    return {
        "frames": out["frames"],
        "events": out["events"],
        "illegal": out["illegal"],
        "done": out["done"],
        "state": out["state"],
        "masks": out["masks"],
        "scores": out["scores"],
        "decisions": out["decisions"],
    }


@app.post("/api/games/{sid}/reset")
def reset_game(sid: str, req: ResetReq) -> dict:
    if sid in four.sessions:
        sess = four.sessions[sid]
        seed = req.seed if req.seed is not None else sess.game.seed
        sess.game.reset(seed)
        from thuai10.fourway.policies import Policy
        sess.bots = [Policy(name, seed+i*1000) for i,name in enumerate(sess.names)]
        return {"game_id": sid, "state": sess.game.snapshot(), "frame": sess.game.frame(), "masks": sess.game.legal_masks()}
    sess = _sess_or_404(sid)
    seed = req.seed if req.seed is not None else sess.game.seed
    sess.game.reset(seed=seed)
    sess.bots.clear()
    sess.ensure_bots()
    return {
        "game_id": sid,
        "state": sess.game.snapshot(),
        "masks": sess.game.legal_masks(),
    }


@app.get("/api/games/{sid}/replay")
def get_replay(sid: str):
    if sid in four.sessions:
        sess = four.sessions[sid]
        return JSONResponse(sess.game.replay({"source": "fourway-web", "policies": sess.names}),
                            headers={"Content-Disposition": f'attachment; filename="thuai10-fourway-{sid}.json"'})
    sess = _sess_or_404(sid)
    replay = replay_of(sess, meta={"source": "web-demo", "human_side": sess.human_side, "bot_names": sess.bot_names, "mode": sess.mode})
    return JSONResponse(
        replay,
        headers={
            "Content-Disposition": f'attachment; filename="thuai10-replay-{sid}.json"'
        },
    )


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "four.html")


if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")
