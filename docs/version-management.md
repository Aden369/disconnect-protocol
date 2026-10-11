# Version Management

`main` contains the current playable prototype. The first tracked release is `v0.5.0`; earlier rules/configurations remain historical files and are not assigned fabricated Git tags.

## Daily changes

Create a short branch such as `feat/base-layout` or `fix/missile-lock`. Commit with `feat:`, `fix:`, `docs:`, or `test:` followed by a concrete description. Open a pull request to `main` with behavior changes and validation; add screenshots when the scene changes.

Run `python -m pytest tests -q` before merging. GitHub Actions runs the same suite. Install the pinned development environment using `python -m pip install -r requirements-dev.txt`.

## Rule releases

Copy the previous balance configuration to a new version before changing mechanics or numbers. Update the current default, versioned rules, replay routing, and observation schema if its shape or encoding changes. Preserve historical configuration and replay fixtures, and verify old replays. Record changes in `CHANGELOG.md`.

After validation, create an annotated tag, for example:

```powershell
git tag -a v0.6.0 -m "Rules v0.6 prototype"
git push origin main --tags
```

Tag names describe prototype releases; they do not imply the competition rules are final.

## Repository contents

Track source, rules, balance files, tests, bundled third-party assets/licenses, and selected replay/evaluation evidence. Caches, virtual environments, credentials, and local editor/agent state are ignored. Write disposable evaluation runs to `results/local/` so committed historical fixtures are preserved.
