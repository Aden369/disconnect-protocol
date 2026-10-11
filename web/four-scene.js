import * as THREE from "./vendor/three.module.js";
import { OrbitControls } from "./vendor/OrbitControls.js";

export const COLORS = [0x45bfff, 0xff647c, 0xb08cff, 0x64ebbc];
export const TEAM_NAMES = ["苍蓝矩阵", "赤焰军团", "紫域干扰", "翡翠堡垒"];
export const NAMES = {
    dog: "机器狗",
    robot: "战斗机甲",
    siege: "破城机",
    drone: "链路无人机",
    hq: "公司核心",
    cannon: "磁轨炮",
    mortar: "电磁迫击炮",
    antiair: "防空激光塔",
    jammer: "干扰阵列",
    wall: "合金城墙",
};
export function behaviorText(a) {
    return a
        ? (a.label || a.kind).replace(
              /dog|robot|siege|drone|hq|cannon|mortar|antiair|jammer|wall/g,
              (t) => NAMES[t],
          )
        : "自主执行任务";
}
let mapCenter = 14;
const position = (x, y, h = 0) =>
    new THREE.Vector3(x - mapCenter, h, y - mapCenter);
const materials = new Map();
function mat(color, glow = false, opacity = 1) {
    const key = [color, glow, opacity].join(":");
    if (!materials.has(key))
        materials.set(
            key,
            new THREE.MeshStandardMaterial({
                color,
                metalness: 0.55,
                roughness: 0.45,
                emissive: glow ? color : 0,
                emissiveIntensity: glow ? 1.5 : 0,
                transparent: opacity < 1,
                opacity,
                depthWrite: opacity === 1,
            }),
        );
    return materials.get(key);
}
function box(parent, size, pos, color, glow = false) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(...size), mat(color, glow));
    m.position.set(...pos);
    m.castShadow = true;
    m.receiveShadow = true;
    parent.add(m);
    return m;
}
function cylinder(
    parent,
    r1,
    r2,
    height,
    pos,
    color,
    glow = false,
    sides = 12,
) {
    const m = new THREE.Mesh(
        new THREE.CylinderGeometry(r1, r2, height, sides),
        mat(color, glow),
    );
    m.position.set(...pos);
    m.castShadow = true;
    m.receiveShadow = true;
    parent.add(m);
    return m;
}
function torus(parent, r, width, pos, color) {
    const m = new THREE.Mesh(
        new THREE.TorusGeometry(r, width, 6, 40),
        mat(color, true),
    );
    m.position.set(...pos);
    m.rotation.x = Math.PI / 2;
    parent.add(m);
    return m;
}

export class FourScene {
    constructor(canvas, labels, onSelect) {
        this.canvas = canvas;
        this.labels = labels;
        this.onSelect = onSelect;
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x070d1b);
        this.scene.fog = new THREE.Fog(0x070d1b, 60, 100);
        this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
        this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFShadowMap;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.15;
        this.camera = new THREE.OrthographicCamera(-24, 24, 16, -16, 0.1, 110);
        this.controls = new OrbitControls(this.camera, canvas);
        this.controls.enableDamping = true;
        this.controls.minPolarAngle = 0.25;
        this.controls.maxPolarAngle = 1.15;
        this.controls.minZoom = 0.7;
        this.controls.maxZoom = 3.5;
        this.resetCamera();
        this.scene.add(new THREE.HemisphereLight(0xc5e2ff, 0x132342, 2.6));
        const sun = new THREE.DirectionalLight(0xb9dcff, 2.8);
        sun.position.set(-15, 30, 15);
        sun.castShadow = true;
        sun.shadow.mapSize.set(2048, 2048);
        Object.assign(sun.shadow.camera, {
            left: -22,
            right: 22,
            top: 22,
            bottom: -22,
            near: 1,
            far: 80,
        });
        sun.shadow.normalBias = 0.035;
        this.scene.add(sun);
        this.entities = new Map();
        this.effectLabels = new Map();
        this.effects = new THREE.Group();
        this.scene.add(this.effects);
        this.nodes = [];
        this.map = null;
        const raycaster = new THREE.Raycaster();
        let down;
        canvas.addEventListener("pointerdown", (e) => {
            down = [e.clientX, e.clientY];
        });
        canvas.addEventListener("pointerup", (e) => {
            if (
                !down ||
                Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5
            )
                return;
            const r = canvas.getBoundingClientRect();
            raycaster.setFromCamera(
                new THREE.Vector2(
                    ((e.clientX - r.left) / r.width) * 2 - 1,
                    (-(e.clientY - r.top) / r.height) * 2 + 1,
                ),
                this.camera,
            );
            const hit = raycaster.intersectObjects(
                [...this.entities.values()].map((e) => e.group),
                true,
            )[0];
            if (hit) {
                let m = hit.object;
                while (m && m.userData.uid === undefined) m = m.parent;
                if (m) this.onSelect(m.userData.uid);
            }
        });
        this.resizeObserver = new ResizeObserver(() => this.resize());
        this.resizeObserver.observe(canvas.parentElement);
        this.resize();
    }
    resetCamera() {
        this.camera.position.set(25, 34, 25);
        this.camera.zoom = 1;
        this.camera.lookAt(0, 0, 0);
        this.camera.updateProjectionMatrix();
        this.controls.target.set(0, 0, 0);
        this.controls.update();
    }
    resize() {
        const r = this.canvas.parentElement.getBoundingClientRect(),
            half = Math.max(
                (this.map?.size || 29) * 0.58,
                ((this.map?.size || 29) * 0.76 * r.height) / r.width,
            );
        this.renderer.setSize(r.width, r.height, false);
        Object.assign(this.camera, {
            left: (-half * r.width) / r.height,
            right: (half * r.width) / r.height,
            top: half,
            bottom: -half,
        });
        this.camera.updateProjectionMatrix();
    }
    configureMap(map) {
        if (JSON.stringify(this.map) === JSON.stringify(map)) return;
        if (this.terrain) {
            this.scene.remove(this.terrain);
            this.terrain.traverse((o) => o.geometry?.dispose());
        }
        this.map = map;
        mapCenter = (map.size - 1) / 2;
        this.nodes = [];
        this.buildTerrain();
        this.resize();
        this.resetCamera();
    }
    buildTerrain() {
        const g = new THREE.Group();
        this.terrain = g;
        this.scene.add(g);
        box(
            g,
            [this.map.size + 1.2, 0.7, this.map.size + 1.2],
            [0, -0.45, 0],
            0x101c32,
        );
        box(
            g,
            [this.map.size + 0.8, 0.12, this.map.size + 0.8],
            [0, -0.05, 0],
            0x33425c,
        );
        for (let x = 0; x < this.map.size; x++)
            for (let y = 0; y < this.map.size; y++)
                box(
                    g,
                    [0.985, 0.05, 0.985],
                    [x - mapCenter, 0.03, y - mapCenter],
                    (x + y) % 2 ? 0x25344b : 0x2d3d53,
                );
        for (let i = -mapCenter; i <= mapCenter; i += 2) {
            box(g, [0.025, 0.015, this.map.size], [i, 0.065, 0], 0x354d6c);
            box(g, [this.map.size, 0.015, 0.025], [0, 0.065, i], 0x354d6c);
        }
        for (let i = 0; i < 4; i++) {
            const c = mapCenter - this.map.hq_local[0];
            const corner = [
                [-c, -c],
                [c, -c],
                [c, c],
                [-c, c],
            ][i];
            box(
                g,
                [
                    (this.map.wall_radius || 2) * 2 - 0.2,
                    0.06,
                    (this.map.wall_radius || 2) * 2 - 0.2,
                ],
                [corner[0], 0.07, corner[1]],
                0x344960,
            );
            torus(g, 1.45, 0.024, [corner[0], 0.12, corner[1]], COLORS[i]);
            for (
                let d = -(this.map.wall_radius || 2) + 1;
                d < (this.map.wall_radius || 2);
                d += 2
            )
                box(
                    g,
                    [0.08, 0.025, (this.map.wall_radius || 2) * 2 - 1.2],
                    [corner[0] + d, 0.11, corner[1]],
                    COLORS[i],
                    true,
                );
        }
        for (const [i, pos] of this.map.nodes.entries()) {
            const n = new THREE.Group();
            n.position.copy(position(...pos));
            cylinder(n, 0.5, 0.65, 0.23, [0, 0.2, 0], 0x536077, false, 6);
            cylinder(n, 0.18, 0.25, 1.1, [0, 0.8, 0], 0x6d839d, false, 6);
            const ring = torus(n, 0.45, 0.045, [0, 1.2, 0], 0x66b8d9);
            torus(n, 1.1, 0.022, [0, 0.1, 0], 0x55748b);
            const core = new THREE.Mesh(
                new THREE.OctahedronGeometry(0.25),
                mat(0x9bdef2, true),
            );
            core.position.y = 1.55;
            n.add(core);
            g.add(n);
            this.nodes.push({ group: n, core, ring });
        }
        // Decorative central uplink is not a resource or victory objective.
        cylinder(g, 1.05, 1.2, 0.2, [0, 0.2, 0], 0x33475d, false, 8);
        torus(g, 0.95, 0.027, [0, 0.32, 0], 0x79a2c7);
        for (let i = 0; i < 4; i++) {
            const a = (i * Math.PI) / 2;
            box(
                g,
                [0.17, 0.18, 0.17],
                [Math.cos(a) * 0.7, 0.38, Math.sin(a) * 0.7],
                0x8097b5,
            );
        }
    }
    createEntity(data) {
        const group = new THREE.Group(),
            body = new THREE.Group();
        group.add(body);
        group.userData.uid = data.uid;
        const color = COLORS[data.player],
            armor = 0x889bb0,
            dark = 0x172339;
        let height = 0.85,
            legs = [];
        if (data.type === "wall") {
            if (data.gate) {
                for (const x of [-0.39, 0.39])
                    box(body, [0.18, 0.9, 0.9], [x, 0.5, 0], 0x54647b);
                box(body, [0.96, 0.15, 0.92], [0, 1, 0], dark);
                box(body, [0.72, 0.025, 0.1], [0, 1.09, 0.37], color, true);
                const panel = new THREE.Mesh(
                    new THREE.BoxGeometry(0.65, 0.68, 0.08),
                    mat(color, true, 0.2),
                );
                panel.position.set(0, 0.53, 0.34);
                body.add(panel);
                body.userData.gatePanel = panel;
            } else {
                box(body, [0.94, 0.82, 0.94], [0, 0.47, 0], 0x536379);
                box(body, [0.98, 0.12, 0.98], [0, 0.92, 0], dark);
                box(body, [0.85, 0.03, 0.1], [0, 1, 0.32], color, true);
            }
            height = 1.15;
        } else if (data.type === "hq") {
            cylinder(body, 0.82, 1.05, 0.25, [0, 0.2, 0], dark, false, 8);
            cylinder(body, 0.63, 0.76, 1, [0, 0.79, 0], armor, false, 8);
            for (let i = 0; i < 4; i++) {
                const a = (i * Math.PI) / 2;
                box(
                    body,
                    [0.3, 1.25, 0.3],
                    [Math.cos(a) * 0.53, 0.88, Math.sin(a) * 0.53],
                    dark,
                );
                box(
                    body,
                    [0.08, 0.75, 0.08],
                    [Math.cos(a) * 0.7, 0.94, Math.sin(a) * 0.7],
                    color,
                    true,
                );
            }
            cylinder(body, 0.26, 0.35, 0.75, [0, 1.52, 0], color, true, 8);
            torus(body, 0.53, 0.045, [0, 1.67, 0], color);
            torus(body, 0.4, 0.035, [0, 2.05, 0], color);
            height = 2.4;
        } else if (data.type === "cannon") {
            cylinder(body, 0.43, 0.56, 0.25, [0, 0.2, 0], dark, false, 8);
            cylinder(body, 0.27, 0.32, 0.32, [0, 0.47, 0], armor);
            const turret = new THREE.Group();
            turret.position.y = 0.67;
            body.add(turret);
            box(turret, [0.45, 0.24, 0.4], [0, 0, 0], dark);
            box(turret, [0.12, 0.11, 0.86], [0, 0.02, 0.4], armor);
            box(turret, [0.15, 0.04, 0.45], [0, 0.1, 0.43], color, true);
            body.userData.turret = turret;
            height = 1.15;
        } else if (data.type === "mortar") {
            cylinder(body, 0.65, 0.72, 0.25, [0, 0.2, 0], dark, false, 8);
            const turret = new THREE.Group();
            turret.position.y = 0.45;
            body.add(turret);
            box(turret, [0.72, 0.22, 0.65], [0, 0, 0], armor);
            const barrel = cylinder(
                turret,
                0.19,
                0.23,
                0.9,
                [0, 0.5, 0.1],
                dark,
            );
            barrel.rotation.x = Math.PI / 6;
            torus(turret, 0.21, 0.035, [0, 0.75, 0.3], color);
            body.userData.turret = turret;
            height = 1.65;
        } else if (data.type === "antiair") {
            cylinder(body, 0.52, 0.65, 0.2, [0, 0.2, 0], dark, false, 6);
            cylinder(body, 0.18, 0.26, 1.3, [0, 0.93, 0], armor, false, 6);
            const turret = new THREE.Group();
            turret.position.y = 1.55;
            body.add(turret);
            for (const x of [-0.22, 0.22])
                box(turret, [0.1, 0.16, 0.7], [x, 0, 0.18], armor);
            box(turret, [0.34, 0.12, 0.24], [0, 0.1, 0], color, true);
            body.userData.turret = turret;
            height = 1.95;
        } else if (data.type === "jammer") {
            cylinder(body, 0.45, 0.55, 0.2, [0, 0.2, 0], dark, false, 8);
            cylinder(body, 0.11, 0.16, 1.1, [0, 0.82, 0], armor);
            for (const h of [0.8, 1.1, 1.4])
                torus(body, 0.3, 0.03, [0, h, 0], color);
            height = 1.85;
        } else if (data.type === "dog") {
            box(body, [0.24, 0.17, 0.47], [0, 0.3, 0], armor);
            box(body, [0.25, 0.16, 0.2], [0, 0.35, 0.29], dark);
            box(body, [0.16, 0.04, 0.04], [0, 0.39, 0.4], color, true);
            for (const x of [-0.15, 0.15])
                for (const z of [-0.17, 0.17])
                    legs.push(
                        box(body, [0.055, 0.23, 0.07], [x, 0.16, z], dark),
                    );
            height = 0.72;
        } else if (data.type === "robot") {
            for (const x of [-0.12, 0.12])
                legs.push(box(body, [0.1, 0.26, 0.12], [x, 0.18, 0], armor));
            box(body, [0.35, 0.32, 0.23], [0, 0.47, 0], dark);
            box(body, [0.25, 0.24, 0.24], [0, 0.76, 0], armor);
            box(body, [0.19, 0.05, 0.035], [0, 0.78, 0.14], color, true);
            box(body, [0.1, 0.1, 0.39], [0.24, 0.48, 0.15], dark);
            height = 1.1;
        } else if (data.type === "siege") {
            box(body, [0.55, 0.23, 0.72], [0, 0.25, 0], armor);
            for (const x of [-0.33, 0.33])
                box(body, [0.15, 0.26, 0.83], [x, 0.18, 0], dark);
            box(body, [0.34, 0.23, 0.34], [0, 0.48, -0.1], dark);
            box(body, [0.13, 0.12, 0.8], [0, 0.56, 0.3], armor);
            box(body, [0.15, 0.035, 0.52], [0, 0.65, 0.37], color, true);
            height = 0.95;
        } else {
            body.position.y = 1.1;
            cylinder(body, 0.18, 0.2, 0.16, [0, 0, 0], armor);
            box(body, [0.11, 0.06, 0.12], [0, 0.11, 0], color, true);
            for (const x of [-0.32, 0.32])
                for (const z of [-0.32, 0.32]) {
                    const arm = box(
                        body,
                        [0.09, 0.06, 0.45],
                        [x / 2, 0, z / 2],
                        dark,
                    );
                    arm.rotation.y = x * z > 0 ? Math.PI / 4 : -Math.PI / 4;
                    const rotor = torus(body, 0.16, 0.02, [x, 0, z], color);
                    rotor.userData.rotor = true;
                }
            height = 1.65;
        }
        if (data.type === "dog") {
            body.scale.setScalar(1.25);
            height *= 1.25;
        }
        if (data.type === "robot") {
            body.scale.setScalar(1.15);
            height *= 1.15;
        }
        const marker = new THREE.Mesh(
            new THREE.RingGeometry(0.4, 0.46, 32),
            new THREE.MeshBasicMaterial({
                color: 0xffdd7b,
                side: THREE.DoubleSide,
            }),
        );
        marker.rotation.x = -Math.PI / 2;
        marker.position.y = 0.12;
        marker.visible = false;
        group.add(marker);
        const health = new THREE.Group();
        health.position.y = height;
        const healthBack = new THREE.Sprite(
            new THREE.SpriteMaterial({ color: 0x12243a, depthTest: false }),
        );
        healthBack.scale.set(0.72, 0.065, 1);
        const healthFill = new THREE.Sprite(
            new THREE.SpriteMaterial({ color, depthTest: false }),
        );
        healthFill.scale.set(0.67, 0.035, 1);
        healthFill.position.z = 0.01;
        health.add(healthBack, healthFill);
        health.visible = data.type !== "wall";
        group.add(health);
        const label = document.createElement("div");
        label.className = "entity-label";
        this.labels.append(label);
        this.scene.add(group);
        return {
            group,
            body,
            label,
            marker,
            height,
            legs,
            data,
            health,
            healthFill,
        };
    }
    projectLabel(label, pos, text, color) {
        const screen = pos.clone().project(this.camera);
        label.style.left = `${(screen.x * 0.5 + 0.5) * this.canvas.clientWidth}px`;
        label.style.top = `${(-screen.y * 0.5 + 0.5) * this.canvas.clientHeight}px`;
        label.style.borderColor = "#" + color.toString(16).padStart(6, "0");
        if (label.innerHTML !== text) label.innerHTML = text;
    }
    effectLabel(key, pos, text, color) {
        let label = this.effectLabels.get(key);
        if (!label) {
            label = document.createElement("div");
            label.className = "effect-label";
            this.labels.append(label);
            this.effectLabels.set(key, label);
        }
        this.effectLabelSeen.add(key);
        this.projectLabel(label, pos, text, color);
    }
    line(a, b, color, dashed = false, opacity = 0.65) {
        const geometry = new THREE.BufferGeometry().setFromPoints([a, b]);
        const line = new THREE.Line(
            geometry,
            dashed
                ? new THREE.LineDashedMaterial({
                      color,
                      dashSize: 0.25,
                      gapSize: 0.16,
                      transparent: true,
                      opacity,
                  })
                : new THREE.LineBasicMaterial({
                      color,
                      transparent: true,
                      opacity,
                  }),
        );
        if (dashed) line.computeLineDistances();
        this.effects.add(line);
        return line;
    }
    ring(center, r, color, opacity = 0.5) {
        const ring = new THREE.Mesh(
            new THREE.RingGeometry(r - 0.035, r, 64),
            new THREE.MeshBasicMaterial({
                color,
                side: THREE.DoubleSide,
                transparent: true,
                opacity,
                depthWrite: false,
            }),
        );
        ring.rotation.x = -Math.PI / 2;
        ring.position.copy(position(...center, 0.12));
        this.effects.add(ring);
        return ring;
    }
    diamond(center, radius, color, opacity = 0.6) {
        const [x, y] = center;
        const points = [
            [x + radius, y],
            [x, y + radius],
            [x - radius, y],
            [x, y - radius],
            [x + radius, y],
        ];
        const line = new THREE.Line(
            new THREE.BufferGeometry().setFromPoints(
                points.map((p) => position(...p, 0.13)),
            ),
            new THREE.LineBasicMaterial({ color, transparent: true, opacity }),
        );
        this.effects.add(line);
    }
    clearEffects() {
        const shared = new Set(materials.values());
        for (const o of this.effects.children) {
            o.geometry?.dispose();
            if (o.material && !shared.has(o.material)) o.material.dispose();
        }
        this.effects.clear();
    }
    draw(frame, previous, alpha, time, selected, showLabels, showNetwork) {
        if (!frame) return;
        this.controls.update();
        this.clearEffects();
        this.effectLabelSeen = new Set();
        const old = new Map(
            [
                ...(previous?.units || []),
                ...(previous?.buildings || []),
                ...(previous?.walls || []),
            ].map((e) => [e.uid, e]),
        );
        const alive = new Set();
        const activity = new Map(frame.activity.map((a) => [a.uid, a]));
        const collisions = new Map();
        for (const data of [
            ...frame.walls,
            ...frame.buildings,
            ...frame.units,
        ]) {
            alive.add(data.uid);
            let e = this.entities.get(data.uid);
            if (!e) {
                e = this.createEntity(data);
                this.entities.set(data.uid, e);
            }
            e.data = data;
            const before = old.get(data.uid) || data,
                x = before.x + (data.x - before.x) * alpha,
                y = before.y + (data.y - before.y) * alpha;
            const key = `${data.x},${data.y}`,
                index = collisions.get(key) || 0;
            collisions.set(key, index + 1);
            const unit = ["dog", "robot", "siege", "drone"].includes(data.type),
                offset = unit ? ((index % 3) - 1) * 0.15 : 0;
            e.group.position.copy(position(x + offset, y - offset, 0.08));
            const a = activity.get(data.uid);
            if (unit) {
                const goal =
                    a?.kind === "attack"
                        ? a.target
                        : [
                              data.x + (data.x - before.x),
                              data.y + (data.y - before.y),
                          ];
                if (goal && (goal[0] !== data.x || goal[1] !== data.y))
                    e.body.rotation.y = Math.atan2(
                        goal[0] - data.x,
                        goal[1] - data.y,
                    );
                if (data.type === "drone")
                    e.body.position.y =
                        1.1 + Math.sin(time * 0.003 + data.uid) * 0.06;
                else
                    e.body.position.y =
                        a?.kind === "move"
                            ? Math.sin(time * 0.02 + data.uid) * 0.035
                            : 0;
                e.legs.forEach(
                    (leg, i) =>
                        (leg.rotation.x =
                            a?.kind === "move"
                                ? Math.sin(time * 0.02 + i * Math.PI) * 0.4
                                : 0),
                );
            } else if (e.body.userData.turret && a?.target)
                e.body.userData.turret.rotation.y = Math.atan2(
                    a.target[0] - data.x,
                    a.target[1] - data.y,
                );
            e.marker.visible = selected === data.uid;
            if (e.body.userData.gatePanel) {
                const open = frame.units.some(
                    (u) =>
                        u.player === data.player &&
                        Math.abs(u.x - data.x) + Math.abs(u.y - data.y) <= 1,
                );
                e.body.userData.gatePanel.scale.y = open ? 0.1 : 1;
                e.body.userData.gatePanel.position.y = open ? 0.88 : 0.53;
            }
            e.health.quaternion.copy(this.camera.quaternion);
            const hpRatio = Math.max(0, data.hp / data.max_hp);
            e.healthFill.scale.x = 0.67 * hpRatio;
            e.healthFill.position.x = -0.335 * (1 - hpRatio);
            e.group.scale.y = data.type === "hq" && data.hp <= 0 ? 0.16 : 1;
            e.label.hidden = !(
                showLabels &&
                (data.type === "hq" || selected === data.uid)
            );
            const labelPos = e.group.position.clone();
            labelPos.y += data.hp <= 0 ? 0.3 : e.height + 0.1;
            labelPos.y += unit ? index * 0.3 : 0;
            const status =
                data.hp <= 0
                    ? "已淘汰"
                    : unit
                      ? behaviorText(a) +
                        (data.jammed
                            ? " · 受屏蔽"
                            : data.linked
                              ? " · 联网"
                              : " · 离线")
                      : `${data.hp}/${data.max_hp} HP${data.jammed && data.attack_interval ? " · EMP射速压制" : ""}`;
            this.projectLabel(
                e.label,
                labelPos,
                `<b>${NAMES[data.type]}${unit ? " #" + data.uid : ""}</b><small>${status}</small>`,
                COLORS[data.player],
            );
        }
        for (const [uid, e] of this.entities)
            if (!alive.has(uid)) {
                this.scene.remove(e.group);
                e.label.remove();
                e.group.traverse((o) => {
                    if (o.isSprite) o.material.dispose();
                    else o.geometry?.dispose();
                });
                this.entities.delete(uid);
            }
        for (const n of frame.nodes) {
            const e = this.nodes[n.index];
            e.core.material = mat(
                n.owner < 0 ? 0x75a3bd : COLORS[n.owner],
                true,
            );
            e.core.rotation.y = time * 0.001;
            e.ring.rotation.z = time * 0.0006;
        }
        for (const a of frame.activity) {
            if (a.kind === "attack") {
                const type = this.entities.get(a.uid)?.data.type;
                if (type === "mortar") {
                    for (let i = 0; i < 10; i++) {
                        const point = (t) =>
                            position(
                                a.from[0] + (a.target[0] - a.from[0]) * t,
                                a.from[1] + (a.target[1] - a.from[1]) * t,
                                0.7 + 12 * t * (1 - t),
                            );
                        this.line(
                            point(i / 10),
                            point((i + 1) / 10),
                            0xffc970,
                            false,
                            0.8,
                        );
                    }
                    this.ring(a.target, 1, 0xffc970, 0.7);
                } else
                    this.line(
                        position(...a.from, type === "antiair" ? 1.65 : 0.65),
                        position(...a.target, type === "antiair" ? 1.1 : 0.6),
                        type === "antiair" ? 0x88efff : COLORS[a.player],
                        false,
                        1 - alpha * 0.5,
                    );
            }
        }
        for (const signal of frame.signals) {
            const color = signal.active ? COLORS[signal.player] : 0x6d6b83;
            this.ring(signal.center, 0.75, color, 0.9);
            const beam = new THREE.Mesh(
                new THREE.CylinderGeometry(0.055, 0.11, 2.3, 8),
                new THREE.MeshBasicMaterial({
                    color,
                    transparent: true,
                    opacity: 0.7,
                }),
            );
            beam.position.copy(position(...signal.center, 1.3));
            this.effects.add(beam);
            this.effectLabel(
                "s" + signal.uid,
                position(...signal.center, 2.7),
                signal.active ? "信号弹 · 制导信标" : "信号被屏蔽",
                color,
            );
        }
        for (const cloud of frame.clouds) {
            const color = COLORS[cloud.player];
            this.diamond(cloud.center, 4, color, 0.7);
            this.diamond(cloud.center, 1 + ((time * 0.001) % 3), color, 0.25);
            const fog = new THREE.Mesh(
                new THREE.CylinderGeometry(4, 4, 0.6, 4, 1, true),
                new THREE.MeshBasicMaterial({
                    color,
                    transparent: true,
                    opacity: 0.12,
                    side: THREE.DoubleSide,
                    depthWrite: false,
                }),
            );
            fog.position.copy(position(...cloud.center, 0.45));
            this.effects.add(fog);
            this.effectLabel(
                "c" + cloud.uid,
                position(...cloud.center, 0.8),
                `EMP 屏蔽 · ${((cloud.until - frame.tick) * 0.5).toFixed(1)}s`,
                color,
            );
        }
        for (const jammer of frame.buildings.filter(
            (b) => b.type === "jammer" && b.hp > 0,
        ))
            this.diamond([jammer.x, jammer.y], 4, COLORS[jammer.player], 0.3);
        for (const m of frame.projectiles) {
            const flight = m.land_tick - m.start,
                p = Math.max(
                    0,
                    Math.min(1, (frame.tick - m.start - 1 + alpha) / flight),
                );
            const point = (t) =>
                position(
                    m.origin[0] + (m.center[0] - m.origin[0]) * t,
                    m.origin[1] + (m.center[1] - m.origin[1]) * t,
                    1.8 +
                        Math.sin(t * Math.PI) * (m.type === "missile" ? 5 : 2),
                );
            const location = point(p),
                color =
                    m.type === "jam"
                        ? 0xb490ff
                        : m.locked
                          ? COLORS[m.player]
                          : 0xffcc66;
            const rocket = new THREE.Mesh(
                new THREE.ConeGeometry(
                    m.type === "missile" ? 0.14 : 0.2,
                    0.6,
                    8,
                ),
                mat(color, true),
            );
            rocket.position.copy(location);
            rocket.quaternion.setFromUnitVectors(
                new THREE.Vector3(0, 1, 0),
                point(Math.min(1, p + 0.02))
                    .sub(point(Math.max(0, p - 0.02)))
                    .normalize(),
            );
            this.effects.add(rocket);
            const trail = new THREE.Line(
                new THREE.BufferGeometry().setFromPoints(
                    Array.from({ length: 12 }, (_, i) =>
                        point(
                            Math.max(0, p - 0.2) + (Math.min(0.2, p) * i) / 11,
                        ),
                    ),
                ),
                new THREE.LineBasicMaterial({
                    color,
                    transparent: true,
                    opacity: 0.6,
                }),
            );
            this.effects.add(trail);
            this.ring(m.center, 1.15, color, 0.6);
            this.effectLabel(
                "m" + m.uid,
                location.clone().add(new THREE.Vector3(0, 0.5, 0)),
                m.type === "jam"
                    ? "屏蔽弹飞行"
                    : m.locked
                      ? "制导导弹"
                      : "导弹失锁",
                color,
            );
        }
        for (const ev of frame.events) {
            if (ev.type === "missile_impact") {
                const burst = new THREE.Mesh(
                    new THREE.SphereGeometry(0.6 + alpha * 1.25, 12, 8),
                    new THREE.MeshBasicMaterial({
                        color: ev.locked ? 0xffb06a : 0x999cab,
                        transparent: true,
                        opacity: (1 - alpha) * 0.65,
                        depthWrite: false,
                    }),
                );
                burst.position.copy(position(...ev.center, 0.45));
                this.effects.add(burst);
            }
        }
        const chosen = activity.get(selected);
        if (chosen?.target)
            this.line(
                position(...chosen.from, 0.2),
                position(...chosen.target, 0.2),
                0xffde80,
                true,
                0.9,
            );
        if (showNetwork) {
            for (const link of frame.network_links || [])
                this.line(
                    position(...link.from, 0.17),
                    position(...link.to, 0.17),
                    COLORS[link.player],
                    true,
                    0.4,
                );
        }
        for (const [key, label] of this.effectLabels)
            if (!this.effectLabelSeen.has(key)) {
                label.remove();
                this.effectLabels.delete(key);
            }
        this.renderer.render(this.scene, this.camera);
    }
}
