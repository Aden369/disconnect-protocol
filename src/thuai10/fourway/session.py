import uuid
from dataclasses import dataclass

from .game import SIDES, FourWayGame
from .policies import Policy


@dataclass
class FourSession:
    game: FourWayGame
    names: list
    bots: list

    def step(self, overrides=None):
        overrides = overrides or {}
        actions = []
        controlled = []
        for i, side in enumerate(SIDES):
            is_controlled = side in overrides
            controlled.append(is_controlled)
            actions.append(
                overrides[side] if is_controlled else self.bots[i].act(self.game, i)
            )
        decisions = [
            {
                "player": i,
                "bot": "human" if controlled[i] else self.names[i],
                "action": action,
                "tick": self.game.tick,
                "reason": "玩家指令"
                if controlled[i]
                else getattr(self.bots[i], "last_reason", ""),
            }
            for i, action in enumerate(actions)
        ]
        result = self.game.step(actions)
        result["decisions"] = decisions
        return result


sessions = {}


def create(seed=10, names=None):
    names = list(names or ["breach", "missile", "electronic", "fortress"])
    if len(names) != 4:
        raise ValueError("四方必须各指定一个策略")
    session = FourSession(
        FourWayGame(seed),
        names,
        [Policy(name, seed + i * 1000) for i, name in enumerate(names)],
    )
    sid = "four-" + uuid.uuid4().hex[:12]
    sessions[sid] = session
    return sid, session
