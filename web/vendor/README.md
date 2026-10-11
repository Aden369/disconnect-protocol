# Third-party rendering dependency

Three.js **0.186.1**, including `OrbitControls`, is bundled from the official npm package (`https://registry.npmjs.org/three/-/three-0.186.1.tgz`). MIT license: [LICENSE](LICENSE).

Files: `three.module.js`, `three.core.js`, `OrbitControls.js`. The controls' bare `three` import is changed to `./three.module.js` for local ES modules. No CDN requests are needed at runtime.

The scene's geometry is created locally in `web/scene.js`; it does not use Clash of Clans assets.
