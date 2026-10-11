import * as THREE from "./vendor/three.module.js";
import { OrbitControls } from "./vendor/OrbitControls.js";

export const NAMES = {
    dog: "机器狗",
    robot: "机器人",
    siege: "攻城车",
    hq: "总部",
    barracks: "兵营",
    cannon: "加农炮",
    shield: "护盾塔",
};
export function behaviorText(a) {
    if (!a) return "等待下一次行动";
    return (a.label || a.kind).replace(
        /dog|robot|siege|hq|barracks|cannon|shield/g,
        (type) => NAMES[type],
    );
}
const COLORS = [0x268ce0, 0xdf604b];
const world = (x, y, h = 0) => new THREE.Vector3(x - 8, h, y - 5);
const materials = new Map();
function material(color) {
    if (!materials.has(color))
        materials.set(
            color,
            new THREE.MeshStandardMaterial({
                color,
                roughness: 0.82,
                metalness: 0.06,
            }),
        );
    return materials.get(color);
}
function box(parent, size, pos, color) {
    const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(...size),
        material(color),
    );
    mesh.position.set(...pos);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
}
function cylinder(parent, r1, r2, h, pos, color, segments = 12) {
    const mesh = new THREE.Mesh(
        new THREE.CylinderGeometry(r1, r2, h, segments),
        material(color),
    );
    mesh.position.set(...pos);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
}
function roof(parent, width, height, pos, color) {
    const mesh = new THREE.Mesh(
        new THREE.ConeGeometry(width, height, 4),
        material(color),
    );
    mesh.rotation.y = Math.PI / 4;
    mesh.position.set(...pos);
    mesh.castShadow = true;
    parent.add(mesh);
    return mesh;
}

export class BattleScene {
    constructor(canvas, labels, onSelect) {
        this.canvas = canvas;
        this.labels = labels;
        this.onSelect = onSelect;
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0xc5d9bf);
        this.scene.fog = new THREE.Fog(0xc5d9bf, 38, 85);
        this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
        this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFShadowMap;
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.25;
        this.camera = new THREE.OrthographicCamera(-15, 15, 10, -10, 0.1, 100);
        this.controls = new OrbitControls(this.camera, canvas);
        this.controls.enableDamping = true;
        this.controls.minPolarAngle = 0.3;
        this.controls.maxPolarAngle = 1.15;
        this.controls.minZoom = 0.65;
        this.controls.maxZoom = 2.8;
        this.controls.enablePan = true;
        this.resetCamera();
        this.scene.add(new THREE.HemisphereLight(0xfff6df, 0x607649, 2.7));
        const sun = new THREE.DirectionalLight(0xffecd2, 3.2);
        sun.position.set(-10, 22, 10);
        sun.castShadow = true;
        sun.shadow.mapSize.set(2048, 2048);
        Object.assign(sun.shadow.camera, {
            left: -18,
            right: 18,
            top: 15,
            bottom: -15,
            near: 1,
            far: 55,
        });
        sun.shadow.bias = -0.0008;
        sun.shadow.normalBias = 0.03;
        this.scene.add(sun);
        this.entities = new Map();
        this.nodes = [];
        this.effects = new THREE.Group();
        this.scene.add(this.effects);
        this.makeTerrain();
        this.raycaster = new THREE.Raycaster();
        this.pointer = new THREE.Vector2();
        let down;
        canvas.addEventListener("pointerdown", (event) => {
            down = [event.clientX, event.clientY];
        });
        canvas.addEventListener("pointerup", (event) => {
            if (
                !down ||
                Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 5
            )
                return;
            const rect = canvas.getBoundingClientRect();
            this.pointer.set(
                ((event.clientX - rect.left) / rect.width) * 2 - 1,
                (-(event.clientY - rect.top) / rect.height) * 2 + 1,
            );
            this.raycaster.setFromCamera(this.pointer, this.camera);
            const hits = this.raycaster.intersectObjects(
                [...this.entities.values()].map((e) => e.group),
                true,
            );
            if (hits.length) {
                let object = hits[0].object;
                while (object && object.userData.uid === undefined)
                    object = object.parent;
                if (object) this.onSelect(object.userData.uid);
            }
        });
        this.resizeObserver = new ResizeObserver(() => this.resize());
        this.resizeObserver.observe(canvas.parentElement);
        this.resize();
    }
    resize() {
        const { width, height } =
            this.canvas.parentElement.getBoundingClientRect();
        this.renderer.setSize(width, height, false);
        const half = 9.2;
        this.camera.left = (-half * width) / height;
        this.camera.right = (half * width) / height;
        this.camera.top = half;
        this.camera.bottom = -half;
        this.camera.updateProjectionMatrix();
    }
    resetCamera() {
        this.camera.position.set(12, 19, 19);
        this.camera.zoom = 1;
        this.camera.lookAt(0, 0, 0);
        this.camera.updateProjectionMatrix();
        this.controls.target.set(0, 0, 0);
        this.controls.update();
    }
    makeTerrain() {
        const terrain = new THREE.Group();
        this.scene.add(terrain);
        box(terrain, [19.5, 0.8, 13.5], [0, -0.5, 0], 0x9a8b68);
        box(terrain, [19.5, 0.18, 13.5], [0, -0.04, 0], 0x7d9d55);
        for (let x = 0; x < 17; x++)
            for (let y = 0; y < 11; y++) {
                const green = [0x9eb96b, 0xa6bd73, 0x9ab267, 0xa1b971][
                    (x * 7 + y * 3) % 4
                ];
                box(terrain, [0.99, 0.045, 0.99], [x - 8, 0.07, y - 5], green);
            }
        // Three roads connect the bases; they are decorative, not movement constraints.
        for (const y of [2, 5, 8])
            for (let x = 0; x < 17; x++) {
                box(
                    terrain,
                    [0.99, 0.03, 0.7],
                    [x - 8, 0.1, y - 5],
                    (x + y) % 2 ? 0xc6b891 : 0xd0c09a,
                );
                if (x > 3 && x < 13)
                    box(
                        terrain,
                        [0.08, 0.02, 0.05],
                        [x - 8 + 0.2, 0.125, y - 5 + 0.16],
                        0xbba67e,
                    );
            }
        for (const sign of [-1, 1]) {
            box(terrain, [3.1, 0.12, 10.5], [sign * 6.4, 0.1, 0], 0xbdba97);
            for (let i = 0; i < 12; i++)
                box(
                    terrain,
                    [0.34, 0.17, 0.4],
                    [sign * 9.5, 0.1, -5.4 + i * 0.98],
                    0xbbb08c,
                );
            for (let y = -5; y <= 5; y += 2.5) {
                cylinder(
                    terrain,
                    0.14,
                    0.19,
                    0.8,
                    [sign * 9.05, 0.45, y],
                    0x896c43,
                    6,
                );
                for (const [r, h, z] of [
                    [0.65, 0.85, 1.2],
                    [0.5, 0.75, 1.7],
                    [0.32, 0.6, 2.05],
                ]) {
                    const tree = new THREE.Mesh(
                        new THREE.ConeGeometry(r, h, 7),
                        material(sign > 0 ? 0x628943 : 0x527d42),
                    );
                    tree.position.set(sign * 9.05, z, y);
                    tree.castShadow = true;
                    terrain.add(tree);
                }
            }
            for (let x = -7.5; x < 8; x += 1.2) {
                const z = sign * 6.05;
                const rock = new THREE.Mesh(
                    new THREE.DodecahedronGeometry(
                        0.18 + (Math.abs(x) % 3) * 0.045,
                    ),
                    material(0xb3b18a),
                );
                rock.position.set(x, 0.17, z);
                rock.scale.y = 0.65;
                terrain.add(rock);
            }
        }
        for (let i = 0; i < 2; i++) {
            const group = new THREE.Group();
            group.position.copy(world(8, i ? 8 : 2));
            cylinder(group, 0.6, 0.7, 0.2, [0, 0.2, 0], 0xc6b58a);
            cylinder(group, 0.48, 0.48, 0.08, [0, 0.35, 0], 0xe7d49e);
            const crystal = new THREE.Mesh(
                new THREE.OctahedronGeometry(0.38),
                new THREE.MeshStandardMaterial({
                    color: 0xf0ce64,
                    emissive: 0xa07d1a,
                    emissiveIntensity: 0.2,
                    roughness: 0.35,
                }),
            );
            crystal.position.y = 0.9;
            crystal.scale.y = 1.5;
            crystal.castShadow = true;
            group.add(crystal);
            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(1.08, 0.025, 6, 48),
                new THREE.MeshBasicMaterial({ color: 0xeddc9b }),
            );
            ring.rotation.x = Math.PI / 2;
            ring.position.y = 0.16;
            group.add(ring);
            this.nodes.push({ group, crystal, ring });
            this.scene.add(group);
        }
    }
    makeEntity(data, isUnit) {
        const group = new THREE.Group(),
            body = new THREE.Group();
        group.add(body);
        group.userData.uid = data.uid;
        const color = COLORS[data.player],
            stone = 0xe0d5b3,
            dark = 0x3b4c47,
            metal = 0xdce5dc;
        let height = 1.1;
        const legs = [];
        if (data.type === "hq") {
            box(body, [1.25, 0.2, 1.1], [0, 0.2, 0], 0xbcb69c);
            box(body, [1, 0.9, 0.8], [0, 0.73, 0], stone);
            roof(body, 0.95, 0.6, [0, 1.48, 0], color);
            box(body, [0.26, 0.42, 0.03], [0, 0.65, 0.42], dark);
            for (const x of [-0.53, 0.53])
                for (const z of [-0.43, 0.43]) {
                    cylinder(body, 0.15, 0.18, 1.05, [x, 0.72, z], stone, 6);
                    roof(body, 0.26, 0.36, [x, 1.4, z], color);
                }
            cylinder(body, 0.025, 0.025, 0.9, [0.15, 1.9, 0], 0x725d3d, 5);
            box(body, [0.4, 0.22, 0.025], [0.35, 2.12, 0], color);
            height = 2.4;
        } else if (data.type === "barracks") {
            box(body, [0.9, 0.16, 0.85], [0, 0.18, 0], 0xb4b399);
            box(body, [0.78, 0.6, 0.73], [0, 0.55, 0], stone);
            roof(body, 0.73, 0.42, [0, 1, 0], color);
            box(body, [0.25, 0.34, 0.025], [0, 0.43, 0.38], dark);
            for (const x of [-0.23, 0.23])
                box(body, [0.13, 0.15, 0.04], [x, 0.64, 0.38], 0x92c0bf);
            height = 1.3;
        } else if (data.type === "cannon") {
            cylinder(body, 0.4, 0.5, 0.3, [0, 0.25, 0], stone, 8);
            cylinder(body, 0.27, 0.3, 0.23, [0, 0.5, 0], color, 8);
            const turret = new THREE.Group();
            body.add(turret);
            turret.position.y = 0.65;
            box(turret, [0.32, 0.25, 0.32], [0, 0, 0], dark);
            box(turret, [0.15, 0.15, 0.65], [0, 0.04, 0.32], dark);
            body.userData.turret = turret;
            height = 1.05;
        } else if (data.type === "shield") {
            cylinder(body, 0.36, 0.42, 0.18, [0, 0.2, 0], stone);
            cylinder(body, 0.15, 0.2, 0.65, [0, 0.58, 0], color, 8);
            const orb = new THREE.Mesh(
                new THREE.IcosahedronGeometry(0.27, 1),
                material(0xb7e1df),
            );
            orb.position.y = 1;
            body.add(orb);
            const aura = new THREE.Mesh(
                new THREE.SphereGeometry(0.68, 16, 12),
                new THREE.MeshBasicMaterial({
                    color,
                    transparent: true,
                    opacity: 0.1,
                    depthWrite: false,
                }),
            );
            aura.position.y = 0.55;
            body.add(aura);
            height = 1.4;
        } else if (data.type === "dog") {
            box(body, [0.22, 0.18, 0.45], [0, 0.31, 0], metal);
            box(body, [0.24, 0.19, 0.2], [0, 0.36, 0.28], color);
            box(body, [0.15, 0.035, 0.03], [0, 0.39, 0.39], 0xffdf69);
            for (const x of [-0.13, 0.13])
                for (const z of [-0.15, 0.15])
                    legs.push(
                        box(body, [0.055, 0.22, 0.06], [x, 0.15, z], dark),
                    );
            box(body, [0.08, 0.04, 0.15], [0, 0.36, -0.29], dark);
            height = 0.67;
        } else if (data.type === "robot") {
            for (const x of [-0.1, 0.1])
                legs.push(box(body, [0.1, 0.22, 0.11], [x, 0.17, 0], dark));
            box(body, [0.3, 0.27, 0.2], [0, 0.43, 0], color);
            box(body, [0.24, 0.22, 0.23], [0, 0.7, 0], metal);
            box(body, [0.17, 0.06, 0.035], [0, 0.72, 0.135], 0x42615b);
            box(body, [0.09, 0.2, 0.1], [-0.22, 0.44, 0], metal);
            box(body, [0.09, 0.09, 0.32], [0.22, 0.48, 0.12], dark);
            height = 1;
        } else {
            box(body, [0.45, 0.19, 0.65], [0, 0.24, 0], color);
            for (const x of [-0.3, 0.3]) {
                box(body, [0.16, 0.23, 0.73], [x, 0.17, 0], dark);
                for (const z of [-0.24, 0, 0.24])
                    cylinder(
                        body,
                        0.09,
                        0.09,
                        0.14,
                        [x, 0.16, z],
                        0x8a958c,
                        8,
                    ).rotation.z = Math.PI / 2;
            }
            box(body, [0.27, 0.19, 0.3], [0, 0.46, -0.08], metal);
            box(body, [0.1, 0.1, 0.6], [0, 0.5, 0.27], dark);
            height = 0.85;
        }
        const hp = new THREE.Group();
        hp.position.y = height;
        const bg = new THREE.Sprite(
            new THREE.SpriteMaterial({ color: 0x304637, depthTest: false }),
        );
        bg.scale.set(0.66, 0.055, 1);
        hp.add(bg);
        const fill = new THREE.Sprite(
            new THREE.SpriteMaterial({ color, depthTest: false }),
        );
        fill.scale.set(0.62, 0.032, 1);
        fill.position.z = 0.01;
        hp.add(fill);
        group.add(hp);
        const marker = new THREE.Mesh(
            new THREE.RingGeometry(0.38, 0.43, 32),
            new THREE.MeshBasicMaterial({
                color: 0xf5d075,
                side: THREE.DoubleSide,
            }),
        );
        marker.rotation.x = -Math.PI / 2;
        marker.position.y = 0.13;
        marker.visible = false;
        group.add(marker);
        const label = document.createElement("div");
        label.className = `entity-label ${data.player ? "red" : "blue"}-label`;
        this.labels.append(label);
        this.scene.add(group);
        return {
            group,
            body,
            hp,
            fill,
            marker,
            label,
            height,
            legs,
            isUnit,
            data,
        };
    }
    clearObjects(group) {
        for (const child of [...group.children]) {
            group.remove(child);
            child.geometry?.dispose();
            if (
                child.material &&
                !materials.has(child.material.color?.getHex())
            )
                child.material.dispose();
        }
    }
    draw(frame, previous, alpha, time, selected, showLabels) {
        if (!frame) return;
        this.controls.update();
        const old = new Map(
            [...(previous?.units || []), ...(previous?.buildings || [])].map(
                (e) => [e.uid, e],
            ),
        );
        const alive = new Set();
        const activity = new Map((frame.activity || []).map((a) => [a.uid, a]));
        const sameCell = new Map();
        for (const data of [...frame.buildings, ...frame.units]) {
            alive.add(data.uid);
            let entry = this.entities.get(data.uid);
            if (!entry) {
                entry = this.makeEntity(data, frame.units.includes(data));
                this.entities.set(data.uid, entry);
            }
            entry.data = data;
            const prev = old.get(data.uid) || data;
            const x = prev.x + (data.x - prev.x) * alpha,
                y = prev.y + (data.y - prev.y) * alpha;
            const overlapKey = `${data.x},${data.y}`;
            const order = sameCell.get(overlapKey) || 0;
            sameCell.set(overlapKey, order + 1);
            // Small formation offsets separate overlapping models; logical tile coordinates remain unchanged.
            const offset = entry.isUnit
                ? order === 0
                    ? 0
                    : order % 2
                      ? 0.18
                      : -0.18
                : 0;
            entry.group.position.copy(world(x + offset, y + offset, 0.13));
            const a = activity.get(data.uid);
            if (entry.isUnit) {
                const dx = data.x - prev.x,
                    dz = data.y - prev.y;
                const aim = a?.kind === "attack" ? a.target : null;
                if (aim)
                    entry.body.rotation.y = Math.atan2(
                        aim[0] - data.x,
                        aim[1] - data.y,
                    );
                else if (Math.abs(dx) + Math.abs(dz) > 0.01)
                    entry.body.rotation.y = Math.atan2(dx, dz);
                const moving = a?.kind === "move";
                entry.body.position.y = moving
                    ? Math.sin(time * 0.018 + data.uid) * 0.035
                    : 0;
                entry.legs.forEach(
                    (leg, i) =>
                        (leg.rotation.x = moving
                            ? Math.sin(time * 0.018 + i * Math.PI) * 0.45
                            : 0),
                );
            } else if (entry.body.userData.turret && a?.target) {
                entry.body.userData.turret.rotation.y = Math.atan2(
                    a.target[0] - data.x,
                    a.target[1] - data.y,
                );
            }
            entry.hp.quaternion.copy(this.camera.quaternion);
            const ratio = Math.max(0, data.hp / data.max_hp);
            entry.fill.scale.x = 0.62 * ratio;
            entry.fill.position.x = -0.31 * (1 - ratio);
            entry.marker.visible = selected === data.uid;
            const projected = entry.group.position.clone();
            projected.y += entry.height + 0.16;
            projected.project(this.camera);
            entry.label.style.left = `${(projected.x * 0.5 + 0.5) * this.canvas.clientWidth}px`;
            entry.label.style.top = `${(-projected.y * 0.5 + 0.5) * this.canvas.clientHeight - (entry.isUnit ? order * 20 : 0)}px`;
            entry.label.hidden = !(
                showLabels &&
                (entry.isUnit || data.type === "hq")
            );
            entry.label.classList.toggle("selected", selected === data.uid);
            const text = `<b>${NAMES[data.type]}${entry.isUnit ? " #" + data.uid : ""}</b><small>${entry.isUnit ? behaviorText(a) : "基地核心"}</small>`;
            if (entry.label.innerHTML !== text) entry.label.innerHTML = text;
        }
        for (const [uid, e] of this.entities)
            if (!alive.has(uid)) {
                this.scene.remove(e.group);
                e.label.remove();
                e.group.traverse((o) => {
                    o.geometry?.dispose();
                    if (o.material?.isSpriteMaterial) o.material.dispose();
                });
                this.entities.delete(uid);
            }
        for (const data of frame.nodes) {
            const n = this.nodes[data.index],
                color = data.owner < 0 ? 0xe4c369 : COLORS[data.owner];
            n.crystal.material.color.setHex(color);
            n.ring.material.color.setHex(color);
            n.crystal.rotation.y = time * 0.0008;
            n.crystal.position.y =
                0.9 + Math.sin(time * 0.002 + data.index) * 0.055;
        }
        this.clearObjects(this.effects);
        // Visual effects depict only attacks actually selected by the simulation.
        for (const a of frame.activity || []) {
            if (a.kind !== "attack") continue;
            const start = world(...a.from, 0.65),
                end = world(...a.target, 0.6);
            const line = new THREE.Line(
                new THREE.BufferGeometry().setFromPoints([start, end]),
                new THREE.LineBasicMaterial({
                    color: a.player ? 0xff9561 : 0x80d7ff,
                    transparent: true,
                    opacity: 1 - alpha * 0.65,
                }),
            );
            this.effects.add(line);
            const shot = new THREE.Mesh(
                new THREE.SphereGeometry(0.065, 6, 6),
                new THREE.MeshBasicMaterial({ color: 0xffef95 }),
            );
            shot.position.copy(start.lerp(end, alpha));
            this.effects.add(shot);
        }
        for (const signal of frame.signals || [])
            this.drawRing(signal.x, signal.y, 0.7, COLORS[signal.player], 0.7);
        for (const bomb of frame.bombs || [])
            this.drawRing(bomb.x, bomb.y, 1.08, 0xf2a243, 0.85);
        for (const event of frame.events || []) {
            if (event.type === "bomb") {
                const fire = new THREE.Mesh(
                    new THREE.SphereGeometry(0.65 + alpha * 0.9, 12, 8),
                    new THREE.MeshBasicMaterial({
                        color: 0xffbe4d,
                        transparent: true,
                        opacity: 0.75 * (1 - alpha),
                        depthWrite: false,
                    }),
                );
                fire.position.copy(world(...event.center, 0.45));
                fire.scale.y = 0.6;
                this.effects.add(fire);
            }
        }
        const chosen = activity.get(selected);
        if (chosen?.target) {
            const line = new THREE.Line(
                new THREE.BufferGeometry().setFromPoints([
                    world(...chosen.from, 0.19),
                    world(...chosen.target, 0.19),
                ]),
                new THREE.LineDashedMaterial({
                    color: 0xf4cd62,
                    dashSize: 0.2,
                    gapSize: 0.15,
                }),
            );
            line.computeLineDistances();
            this.effects.add(line);
        }
        this.renderer.render(this.scene, this.camera);
    }
    drawRing(x, y, r, color, opacity) {
        const ring = new THREE.Mesh(
            new THREE.RingGeometry(r - 0.035, r, 48),
            new THREE.MeshBasicMaterial({
                color,
                transparent: true,
                opacity,
                side: THREE.DoubleSide,
            }),
        );
        ring.rotation.x = -Math.PI / 2;
        ring.position.copy(world(x, y, 0.17));
        this.effects.add(ring);
    }
}
