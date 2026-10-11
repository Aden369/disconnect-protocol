# Repository Guidelines

## Project Structure & Module Organization

THUAI10 is an EESAST AI competition prototype. `src/thuai10/core/` contains deterministic rules; `bots/` contains decision algorithms; `server/` exposes local HTTP sessions; `env/` retains the legacy two-agent interface. `src/thuai10/fourway/` provides the current four-agent rules, policies, network warfare, and training environment. `web/` contains the Three.js spectator UI and bundled MIT dependencies. Balance configurations live in `configs/`, tests in `tests/`, scripts in `scripts/`, design/review documents in `docs/`, and evaluation artifacts in `results/`.

## Build, Test, and Development Commands

Run from the repository root:

- `python scripts/serve.py --port 8000`: start the local 3D demo.
- `python -m pytest tests -q`: run core, server, replay, and observation tests.
- `python scripts/run_fourway.py --mode scripts --games 24`: evaluate all strategy/position permutations.
- `python scripts/run_fourway.py --mode random --games 100 --out results/fourway-random.json`: check four-agent random episodes.

See README for dependencies. The frontend uses local ES modules without a build step. Tests and scripts load `src` automatically; standalone module commands in PowerShell require `$env:PYTHONPATH="src"`.

## Coding Style & Naming Conventions

Use UTF-8, four-space indentation, descriptive identifiers, Python `snake_case`, and consistent JavaScript naming. Markdown filenames use lowercase hyphenated names. Format frontend sources with Prettier using four spaces and Python sources with Ruff; leave bundled third-party code untouched. Keep numeric rules in the versioned configuration; rendering must not calculate combat outcomes.

## Testing Guidelines

Use pytest. Name tests `test_<behavior>`. Prioritize simultaneous combat, economy, observation completeness, deterministic seeds, mirrored coordinates, and replay compatibility. Verify visible changes in a browser; API tests alone cannot establish visual quality. No coverage threshold is established.

## Commit & Pull Request Guidelines

Use the `type: description` convention, such as `fix: allocate observation slots for new units`. PRs should explain behavior, link related issues when available, report validation, and include screenshots for scene changes. Version rule and observation changes explicitly.

## Agent Instructions

Long tasks need a five-minute heartbeat initially, then thirty or sixty minutes once stable; stop it on completion. Avoid unnecessary safety checks. Keep source ideas, proposed changes, and unverified balance assumptions distinct. The demo defaults to four algorithms fighting simultaneously. Energy and relay ownership must never determine victory; the last surviving core wins.

## Feishu Account Selection

Robomaster Laboratory: MCP `feishu-docs`, CLI `--profile cli_aa2a0bcab578dccd`. EESAST Software Department: MCP `feishu-kexie`, CLI `--profile kexie-software`. Always specify the profile, never switch global defaults, and ask if ownership is unclear. Continue supported document work while search approval is pending. Integration instructions: `C:\Users\31024\.local\share\feishu-desktop`.
