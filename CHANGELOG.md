# Changelog

## v0.6.0 — 2026-10-11

- Adapt grid-targeted tactical skills and tower suppression from the teammate Sovereign design, retaining four-way real-time play.
- Accept structured signal/missile/EMP coordinates alongside the existing 41 integer actions.
- Make enemy tower attack intervals double under EMP or fixed interference; show suppression and ground impacts in the spectator UI.
- Version replays and observations as v0.6; retain v0.3–v0.5 replay compatibility.


- Experiment with missile ground clusters and frontline EMP targeting; record stationary/moving controls and real-match limitations.
- Explain tactical ground-skill decisions in the spectator UI and preserve in-flight missile beacons.

- Consolidate current documentation under a single index and rules file.
- Archive old rules/plans/review reports by version and repair relative links.

## v0.5.0 — 2026-10-11

First Git baseline of the current playable prototype; rules and balance version v0.5.

- Expand the arena to 29×29 and each base to 9×9, with a 7×7 interior.
- Add ground splash mortars, dedicated air defense, and distinct defense models.
- Extend training observations to 2,681 values and 38 structure slots per faction.
- Audit documentation against implemented networking, targeting, and timing behavior.
- Validate 109 tests, 24 strategy permutations, 12 random games, and historical replay compatibility.

## Earlier design versions

These are preserved configuration/document versions, not reconstructed Git releases.

- **v0.4:** unarmed support drones, two-drone cap, ground-only relay capture, explicit troop roles and air defense restrictions.
- **v0.3:** four-way continuous combat, communication links, destructible walls, guided missiles and EMP; elimination determines victory.
- **v0.1–v0.2:** legacy two-agent, phased prototypes retained for replay compatibility.

See versioned files in `configs/`, `docs/`, and checked-in evidence in `results/`.
