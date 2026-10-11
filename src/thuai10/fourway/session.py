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
        actions = (
            [self.bots[i].act(self.game, i) for i in range(4)]
            if overrides is None
            else [overrides.get(side, 0) for side in SIDES]
        )
        decisions = [
            {
                "player": i,
                "bot": self.names[i],
                "action": action,
                "tick": self.game.tick,
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
