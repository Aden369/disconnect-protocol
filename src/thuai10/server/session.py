"""本地服务：创建对局、step、导出回放。前端不另算伤害或胜负。"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from thuai10.bots import SCRIPT_BOTS, make_bot
from thuai10.core.config import BalanceConfig, load_config
from thuai10.core.engine import Game
from thuai10.core.replay import record


@dataclass
class Session:
    game: Game
    mode: str                     # human / watch
    human_side: Optional[str]     # left / right / None
    bot_names: dict[str, str]
    bots: dict[str, Any] = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)

    def ensure_bots(self) -> None:
        need = []
        if self.mode == "watch":
            need = ["left", "right"]
        elif self.mode == "human":
            need = [s for s in ("left", "right") if s != self.human_side]
        for side in need:
            if side not in self.bots:
                self.bots[side] = make_bot(self.bot_names.get(side, "turtle"), seed=self.game.seed + (0 if side == "left" else 1000))

    def bot_action(self, side: str) -> Optional[int]:
        bot = self.bots.get(side)
        if bot is None:
            return None
        player = 0 if side == "left" else 1
        return bot.act(self.game.state, player, self.game.cfg)


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    def create(
        self,
        mode: str = "watch",
        human_side: str = "left",
        seed: int = 0,
        bot_left: str = "node_grabber",
        bot_right: str = "tech_siege",
        config: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> tuple[str, Session]:
        cfg = load_config(config)
        game = Game(cfg, seed=seed)
        sess = Session(
            game=game,
            mode=mode,
            human_side=human_side if mode == "human" else None,
            bot_names={"left": bot_left, "right": bot_right},
            meta=meta or {},
        )
        sess.ensure_bots()
        sid = uuid.uuid4().hex[:12]
        self.sessions[sid] = sess
        return sid, sess

    def get(self, sid: str) -> Session:
        if sid not in self.sessions:
            raise KeyError(sid)
        return self.sessions[sid]


store = SessionStore()


def step_session(sess: Session, human_action: Optional[int]) -> dict:
    """推进一个决策步：对手脚本只读取旧状态，双方动作统一结算。"""
    a_left = human_action if sess.human_side == "left" else sess.bot_action("left")
    a_right = human_action if sess.human_side == "right" else sess.bot_action("right")
    from thuai10.core.actions import decode
    decisions = []
    for side, aid in (("left", a_left), ("right", a_right)):
        action = decode(aid, sess.game.cfg)
        decisions.append({"side": side, "bot": sess.bot_names[side],
                          "action": action.__dict__, "tick": sess.game.state.tick,
                          "phase": sess.game.state.phase})
    out = sess.game.step({"left": a_left, "right": a_right})
    out["masks"] = sess.game.legal_masks()
    out["scores"] = sess.game.scores()
    out["decisions"] = decisions
    return out


def replay_of(sess: Session, meta: Optional[dict] = None) -> dict:
    return record(sess.game, meta=meta or dict(sess.meta))
