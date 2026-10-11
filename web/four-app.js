import {
    FourScene,
    COLORS,
    TEAM_NAMES,
    NAMES,
    behaviorText,
} from "./four-scene.js";
const $ = (id) => document.getElementById(id);
const POLICY_NAMES = {
    breach: "破墙突击",
    missile: "信标制导",
    electronic: "电子战压制",
    fortress: "堡垒反击",
};
const REGION_NAMES = [
    "西北基地",
    "北侧",
    "东北基地",
    "西侧",
    "中央",
    "东侧",
    "西南基地",
    "南侧",
    "东南基地",
];
const ROLES = {
    dog: "抢点 / 近战",
    robot: "护卫 / 防空",
    siege: "拆墙 / 攻城",
    drone: "通信 / 无武装",
};
const hex = (i) => "#" + COLORS[i].toString(16).padStart(6, "0");
const app = {
    id: null,
    frame: null,
    previous: null,
    queue: [],
    cursor: 0,
    fraction: 0,
    busy: false,
    paused: true,
    speed: 2,
    selected: null,
    generation: 0,
    events: [],
    config: null,
    terminal: null,
    time: 0,
    policies: [],
};
let scene;
try {
    scene = new FourScene($("board"), $("labels"), (uid) => {
        app.selected = uid;
        updateUnits();
    });
} catch (e) {
    $("scene-error").hidden = false;
    $("scene-error").textContent = "3D 初始化失败：" + e.message;
}
async function api(path, body) {
    const r = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    return data;
}
async function newGame() {
    const gen = ++app.generation;
    app.busy = true;
    app.paused = true;
    app.queue = [];
    app.terminal = null;
    try {
        const policies = Array.from(
            { length: 4 },
            (_, i) => $("policy-" + i).value,
        );
        const data = await api("/api/games", {
            mode: "four",
            seed: Number($("seed").value) || 0,
            policies,
        });
        if (gen !== app.generation) return;
        Object.assign(app, {
            id: data.game_id,
            config: data.config,
            frame: data.frame,
            previous: data.frame,
            cursor: 0,
            fraction: 0,
            events: [],
            selected: null,
            time: 0,
            policies,
        });
        scene?.configureMap(data.config.map);
        $("events").replaceChildren();
        $("result").hidden = true;
        $("decisions").innerHTML =
            '<p class="subtle">四个算法基于同一战场状态同时决策。</p>';
        app.paused = false;
        updateUI();
    } catch (e) {
        log("连接失败：" + e.message, 0);
    } finally {
        if (gen === app.generation) {
            app.busy = false;
            controls();
        }
    }
}
async function requestStep() {
    if (app.busy || !app.id || app.terminal || app.queue.length) return;
    const gen = app.generation,
        id = app.id;
    app.busy = true;
    try {
        const out = await api(`/api/games/${id}/step`, {});
        if (gen !== app.generation) return;
        app.queue = out.frames;
        app.cursor = 0;
        app.fraction = 0;
        app.events.push(...out.events);
        app.terminal = out.done ? out.state : null;
        $("decisions").innerHTML = out.decisions
            .map(
                (d) =>
                    `<div class="order" style="--team:${hex(d.player)}"><b>${TEAM_NAMES[d.player]}</b><small>${POLICY_NAMES[d.bot]} / ${(d.tick * 0.5).toFixed(1)}s</small><p>${describe(d.action)}</p></div>`,
            )
            .join("");
    } catch (e) {
        if (gen === app.generation) {
            app.paused = true;
            log("推进失败：" + e.message, app.frame?.tick || 0);
        }
    } finally {
        if (gen === app.generation) {
            app.busy = false;
            controls();
        }
    }
}
function advance() {
    if (!app.queue.length) return;
    app.previous = app.frame;
    app.frame = app.queue[app.cursor++];
    for (const e of app.events.filter((e) => e.tick <= app.frame.tick))
        logEvent(e);
    app.events = app.events.filter((e) => e.tick > app.frame.tick);
    if (app.cursor >= app.queue.length) {
        app.queue = [];
        app.cursor = 0;
        app.fraction = 0;
        app.previous = app.frame;
    }
    updateUI();
    if (app.terminal && !app.queue.length) showResult();
}
function controls() {
    const finished = !!(app.terminal && !app.queue.length);
    $("pause").textContent = finished ? "已结束" : app.paused ? "继续" : "暂停";
    $("pause").disabled = finished;
    $("step").disabled = app.busy || finished;
}
function updateUI() {
    const f = app.frame;
    if (!f) return;
    const sec = f.tick * 0.5;
    $("clock").textContent =
        `${String(Math.floor(sec / 60)).padStart(2, "0")}:${(sec % 60).toFixed(1).padStart(4, "0")}`;
    $("phase").textContent = f.done
        ? "对局结束"
        : f.phase === "overload"
          ? "全域过载 · 决胜阶段"
          : "常规作战 · 链路争夺";
    $("alive-count").textContent = f.players.filter((p) => p.alive).length;
    $("progress").style.width =
        `${(f.tick / app.config.time.max_ticks) * 100}%`;
    $("factions").innerHTML = f.players
        .map(
            (p) =>
                `<div class="faction ${p.alive ? "" : "dead"}" style="--team:${hex(p.index)}"><b>${TEAM_NAMES[p.index]}</b><small>${p.alive ? POLICY_NAMES[app.policies[p.index]] : "已淘汰 " + (p.eliminated_tick * 0.5).toFixed(1) + "s"}</small><div class="health"><i style="width:${(p.hq.hp / p.hq.max_hp) * 100}%"></i></div><div class="metrics">核心 ${p.hq.hp} HP · ${p.unit_count} 部队 · 能量 ${p.resources}</div></div>`,
        )
        .join("");
    $("node-status").innerHTML = f.nodes
        .map(
            (n) =>
                `<span style="color:${n.owner < 0 ? "#6d8fa9" : hex(n.owner)}">R${n.index + 1} · ${n.owner < 0 ? "中立" : TEAM_NAMES[n.owner]}${n.progress ? " " + n.progress + "/4" : ""}</span>`,
        )
        .join("");
    $("systems").innerHTML = f.players
        .map(
            (p) =>
                `<div class="system-row" style="--team:${hex(p.index)}"><div><b>${TEAM_NAMES[p.index]}</b><small> ${p.alive ? "联网 " + p.linked_count + "/" + p.unit_count : "核心离线"}</small></div><span>导弹 CD ${Math.max(0, p.cooldowns.missile - f.tick) * 0.5}s<br>中继 ${p.relay_count} · 维修 ${p.repairs}/5</span></div>`,
        )
        .join("");
    if (!f.done)
        $("lesson").textContent =
            f.phase === "overload"
                ? "120 秒后全域过载：各核心持续受到递增的真实伤害。修复和资源不能被换算成胜负分。"
                : "中继扩展指挥范围，信号弹引导部队并锁定导弹；EMP 可断链和解除制导。离线部队继续旧指令，陆军要先破墙。";
    updateUnits();
    controls();
}
function updateUnits() {
    const f = app.frame;
    if (!f) return;
    const activity = new Map(f.activity.map((a) => [a.uid, a]));
    $("unit-count").textContent =
        f.units.length +
        "兵 / " +
        f.buildings.filter((b) => b.type !== "hq" && b.hp > 0).length +
        "设施";
    $("unit-list").replaceChildren();
    for (const u of [
        ...f.units,
        ...f.buildings.filter(
            (b) =>
                ["cannon", "mortar", "antiair", "jammer"].includes(b.type) &&
                b.hp > 0,
        ),
    ]) {
        const row = document.createElement("button");
        row.className =
            "unit-row " + (u.uid === app.selected ? "selected" : "");
        row.style.setProperty("--team", hex(u.player));
        row.innerHTML = `<b>${NAMES[u.type]} #${u.uid} · ${u.hp}HP · ${ROLES[u.type] || { cannon: "拦截", mortar: "地面范围打击", antiair: "防空", jammer: "通信干扰" }[u.type]}</b><small>${u.type === "jammer" ? "持续屏蔽附近敌方通信" : behaviorText(activity.get(u.uid))}</small>`;
        row.onclick = () => {
            app.selected = u.uid;
            updateUnits();
        };
        $("unit-list").append(row);
    }
    const selected = [...f.units, ...f.buildings, ...f.walls].find(
            (e) => e.uid === app.selected,
        ),
        a = activity.get(app.selected);
    $("selected-info").textContent = selected
        ? `${TEAM_NAMES[selected.player]} ${NAMES[selected.type]} #${selected.uid} · ${selected.hp}/${selected.max_hp}HP · ${ROLES[selected.type] || "设施"} · 格(${selected.x},${selected.y}) · ${selected.type === "wall" ? (selected.gate ? "授权门：己方可通过，敌方需破门" : "阻挡地面移动与敌方射线") : behaviorText(a)}${a?.target ? " → 目标(" + a.target.join(",") + ")" : ""}${selected.linked !== undefined ? " · " + (selected.jammed ? "受屏蔽" : selected.linked ? "在线" : "离线") : ""}`
        : app.selected !== null
          ? "该实体已被摧毁。"
          : "点击单位或城墙查看行为、目标、通信状态与生命。";
}
function describe(a) {
    if (!a) return "维持自主任务";
    if (a <= 4)
        return "生产 " + NAMES[["dog", "robot", "siege", "drone"][a - 1]];
    if (a <= 9)
        return {
            5: "加建磁轨炮",
            6: "部署固定干扰阵列",
            7: "加固存活城墙",
            8: "维修公司核心",
            9: "升级作战科技",
        }[a];
    if (a <= 13) return "进攻目标 → " + TEAM_NAMES[a - 10];
    if (a <= 22) return "发射信号弹 → " + REGION_NAMES[a - 14];
    if (a <= 31) return "发射制导导弹 → " + REGION_NAMES[a - 23];
    return "发射信号屏蔽弹 → " + REGION_NAMES[a - 32];
}
function log(text, tick) {
    const li = document.createElement("li"),
        t = document.createElement("time");
    t.textContent = (tick * 0.5).toFixed(1) + "s";
    li.append(t, document.createTextNode(text));
    $("events").prepend(li);
    while ($("events").children.length > 60)
        $("events").lastElementChild.remove();
}
function logEvent(e) {
    const team = e.player === undefined ? "" : TEAM_NAMES[e.player];
    let text;
    switch (e.type) {
        case "deploy":
            text = `${team}部署 ${e.count} 个${NAMES[e.unit]}`;
            break;
        case "build":
            text = `${team}建造${NAMES[e.building]}`;
            break;
        case "signal":
            text = `${team}发出信号弹，建立制导信标`;
            break;
        case "missile_launch":
            text = `${team}发射制导导弹，4 秒后命中`;
            break;
        case "jam_launch":
            text = `${team}发射信号屏蔽弹`;
            break;
        case "jam_cloud":
            text = `${team}展开 EMP 云，干扰其他方通信`;
            break;
        case "lock_lost":
            text = `${team}导弹失锁，伤害降至 ${app.config.missile.lost_damage}`;
            break;
        case "missile_impact":
            text = `${team}${e.locked ? "制导命中" : "失锁落弹"}，${e.damage}伤害 / ${e.hit.length}目标`;
            break;
        case "wall_destroyed":
            text = `${team}城墙被突破`;
            break;
        case "eliminated":
            text = `${team}核心摧毁，已淘汰`;
            break;
        case "node_flip":
            text = `${team}取得中继 R${e.node + 1}`;
            break;
        case "repair":
            text = `${team}修复核心 ${e.healed}HP`;
            break;
        case "target":
            text = `${team}将进攻对象改为${TEAM_NAMES[e.target]}`;
            break;
        case "overload":
            text = `全域过载：存活核心受到 ${e.damage} 伤害`;
            break;
        case "tech":
            text = `${team}升级作战科技`;
            break;
        default:
            return;
    }
    log(text, e.tick);
}
function showResult() {
    const s = app.terminal;
    if (!s) return;
    app.paused = true;
    $("result").hidden = false;
    const living = s.players
        .filter((p) => p.eliminated_tick === null)
        .map((p) => TEAM_NAMES[p.index]);
    const message =
        s.winner >= 0
            ? TEAM_NAMES[s.winner] + "获胜 · 最后存活者"
            : s.end_reason === "mutual_destruction"
              ? "最终各方同归于尽 · 平局"
              : "时间上限 · " + living.join("、") + "并列存活，无冠军";
    $("result").textContent = message;
    $("lesson").textContent =
        message + "。能量、中继控制时长和击杀均不参与判胜。";
    controls();
}
$("pause").onclick = () => {
    app.paused = !app.paused;
    if (!app.paused) {
        app.previous = app.frame;
        app.fraction = 0;
    }
    controls();
};
$("step").onclick = async () => {
    app.paused = true;
    if (!app.queue.length) await requestStep();
    advance();
    app.fraction = 0;
    controls();
};
$("restart").onclick = newGame;
$("apply").onclick = newGame;
$("camera").onclick = () => scene?.resetCamera();
document.querySelectorAll("[data-speed]").forEach(
    (b) =>
        (b.onclick = () => {
            app.speed = Number(b.dataset.speed);
            document
                .querySelectorAll("[data-speed]")
                .forEach((e) => e.classList.toggle("active", e === b));
        }),
);
$("replay").onclick = () => {
    if (app.id) {
        const link = document.createElement("a");
        link.href = `/api/games/${app.id}/replay`;
        link.download = "fourway-replay.json";
        link.click();
    }
};
let last = performance.now();
function loop(time) {
    const dt = Math.min(100, time - last);
    last = time;
    if (!app.paused) {
        app.time += dt;
        if (app.queue.length) {
            app.fraction += dt / (500 / app.speed);
            while (app.fraction >= 1 && app.queue.length) {
                app.fraction -= 1;
                advance();
            }
        } else if (!app.terminal) requestStep();
    }
    scene?.draw(
        app.frame,
        app.previous,
        app.paused || !app.queue.length ? 1 : app.fraction,
        app.time,
        app.selected,
        $("show-labels").checked,
        $("show-links").checked,
    );
    requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
newGame();
