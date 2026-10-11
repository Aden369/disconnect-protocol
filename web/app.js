import { BattleScene, NAMES, behaviorText } from "./scene.js";

const $ = (id) => document.getElementById(id);
const BOT_NAMES = {
    node_grabber: "抢点扩张",
    robot_push: "机器人推进",
    tech_siege: "科技攻城",
    turtle: "基地防守",
};
const BOT_DESC = {
    node_grabber: "机器狗分路争点，机器人进攻",
    robot_push: "机器人正面推进，集中火力",
    tech_siege: "升级科技，攻城车突破基地",
    turtle: "炮塔与护盾守城，反击来犯单位",
};
const PHASE = { build: "构建", layout: "布局", repair: "维修", attack: "进攻" };
const LESSON = {
    build: "双方算法各选一项建设：扩军、加固或升级科技。资源有限，本轮只能投资一个方向。",
    layout: "算法将炮塔调整到合适位置。建筑可以移动或交换，总部固定不动。",
    repair: "算法决定是否花 20 资源修复建筑 80 HP。维修与扩军共用同一份预算。",
    attack: "机器狗守节点，机器人与攻城车攻基地。射程内优先交火；信号临时改目标，圈出的轰炸区两秒后落弹。",
};
const app = {
    id: null,
    frame: null,
    previous: null,
    queue: [],
    cursor: 0,
    fraction: 0,
    busy: false,
    paused: false,
    speed: 2,
    selected: null,
    generation: 0,
    pendingEvents: [],
    config: null,
    decisions: [],
    terminal: null,
    animationTime: 0,
};
let scene;
try {
    scene = new BattleScene($("board"), $("labels"), (uid) => {
        app.selected = uid;
        updateUnits();
    });
} catch (error) {
    $("scene-error").hidden = false;
    $("scene-error").textContent = "3D 场景无法初始化：" + error.message;
}

async function api(path, body) {
    const res = await fetch(
        path,
        body === undefined
            ? {}
            : {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(body),
              },
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    return data;
}
async function newGame() {
    const generation = ++app.generation;
    app.busy = true;
    app.paused = true;
    app.queue = [];
    app.terminal = null;
    try {
        const left = $("bot-left").value,
            right = $("bot-right").value;
        const data = await api("/api/games", {
            mode: "watch",
            seed: Number($("seed").value) || 0,
            bot_left: left,
            bot_right: right,
        });
        if (generation !== app.generation) return;
        app.id = data.game_id;
        app.config = data.config;
        app.frame = data.frame;
        app.previous = data.frame;
        app.cursor = 0;
        app.fraction = 0;
        app.selected = null;
        app.pendingEvents = [];
        app.decisions = [];
        $("events").replaceChildren();
        $("result").hidden = true;
        for (const [i, name] of [
            [0, left],
            [1, right],
        ]) {
            $("name-" + i).textContent = BOT_NAMES[name];
            $("strategy-" + i).textContent = BOT_DESC[name];
        }
        $("decisions").innerHTML =
            '<p class="subtle">双方算法读取相同的旧战场状态，同时决策。</p>';
        app.paused = false;
        updateUI();
    } catch (error) {
        logMessage("连接失败：" + error.message, 0);
    } finally {
        if (generation === app.generation) {
            app.busy = false;
            updateControls();
        }
    }
}
async function requestStep() {
    if (app.busy || !app.id || app.terminal || app.queue.length) return;
    const generation = app.generation,
        id = app.id;
    app.busy = true;
    try {
        const data = await api(`/api/games/${id}/step`, {});
        if (generation !== app.generation) return;
        app.queue = data.frames;
        app.cursor = 0;
        app.fraction = 0;
        app.pendingEvents.push(...data.events);
        app.decisions = data.decisions || [];
        app.terminal = data.done ? data.state : null;
        updateDecisions();
        if (!app.queue.length && app.terminal) showResult();
    } catch (error) {
        if (generation === app.generation) {
            app.paused = true;
            logMessage("推进失败：" + error.message, app.frame?.tick || 0);
        }
    } finally {
        if (generation === app.generation) {
            app.busy = false;
            updateControls();
        }
    }
}
function advanceFrame() {
    if (!app.queue.length) return;
    app.previous = app.frame;
    app.frame = app.queue[app.cursor++];
    const now = app.frame.tick;
    for (const event of app.pendingEvents.filter((e) => e.tick <= now))
        logEvent(event);
    app.pendingEvents = app.pendingEvents.filter((e) => e.tick > now);
    if (app.cursor >= app.queue.length) {
        app.queue = [];
        app.cursor = 0;
        app.fraction = 0;
        app.previous = app.frame;
        if (app.terminal) showResult();
    }
    updateUI();
}
function updateControls() {
    $("pause").textContent = app.paused ? "继续" : "暂停";
    $("step").disabled = app.busy || !!(app.terminal && !app.queue.length);
}
function updateUI() {
    const frame = app.frame;
    if (!frame) return;
    const seconds = frame.tick * (app.config?.time.tick_seconds || 0.5);
    $("clock").textContent =
        `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
    $("round").textContent =
        `ROUND ${String(frame.round + 1).padStart(2, "0")} / ${String(app.config.time.rounds).padStart(2, "0")}`;
    $("phase").textContent =
        (frame.winner === null ? PHASE[frame.phase] : "结算") + "阶段";
    $("progress").style.width = `${(frame.tick / 360) * 100}%`;
    $("lesson").textContent = LESSON[frame.phase];
    $("companies").innerHTML = frame.players
        .map((p, i) => {
            const hp = Math.max(0, p.hq.hp),
                reserves = p.units.filter((u) => !u.on_field).length;
            return `<div class="company ${i ? "red" : "blue"}"><div class="company-heading"><b>${i ? "红" : "蓝"}方总部</b><span>${hp} / ${p.hq.max_hp} HP</span></div><div class="health"><div style="width:${(hp / p.hq.max_hp) * 100}%"></div></div><div class="metrics"><span>资源<b>${p.resources}</b></span><span>科技 / 预备队<b>Lv.${p.tech} / ${reserves}</b></span><span>得分<b>${p.score.toFixed(1)}</b></span></div></div>`;
        })
        .join("");
    for (const node of frame.nodes) {
        const el = $("node-" + node.index);
        el.textContent = `${node.index ? "南" : "北"}节点 · ${node.owner < 0 ? "中立" : node.owner ? "红方控制" : "蓝方控制"}${node.progress ? " · 占领 " + node.progress + "/4" : ""}`;
        el.style.color =
            node.owner < 0 ? "#8a783b" : node.owner ? "#c55740" : "#217fc9";
    }
    updateUnits();
    updateControls();
}
function updateUnits() {
    const frame = app.frame;
    if (!frame) return;
    const activities = new Map((frame.activity || []).map((a) => [a.uid, a]));
    $("unit-count").textContent = frame.units.length + " 个在场";
    $("unit-list").replaceChildren();
    for (const unit of frame.units) {
        const row = document.createElement("button");
        row.className =
            "unit-row " + (unit.uid === app.selected ? "selected" : "");
        row.innerHTML = `<span class="${unit.player ? "red" : "blue"}">${NAMES[unit.type]} #${unit.uid} · ${unit.hp}HP</span><small>${behaviorText(activities.get(unit.uid))}</small>`;
        row.onclick = () => {
            app.selected = unit.uid;
            updateUnits();
        };
        $("unit-list").append(row);
    }
    if (!frame.units.length)
        $("unit-list").innerHTML =
            '<p class="subtle">部队在基地等待部署。进入进攻阶段后算法自动出兵。</p>';
    const selected = [...frame.units, ...frame.buildings].find(
            (u) => u.uid === app.selected,
        ),
        a = activities.get(app.selected);
    $("selected-info").textContent = selected
        ? `${selected.player ? "红" : "蓝"}方 ${NAMES[selected.type]} #${selected.uid} · ${selected.hp}/${selected.max_hp} HP · 当前格 (${selected.x},${selected.y}) · ${behaviorText(a)}${a?.target ? " → 目标格 (" + a.target.join(",") + ")" : ""}`
        : app.selected !== null
          ? "此单位已阵亡或返回预备队。"
          : "点击单位查看目标和行为，金色虚线连接其当前目标。";
}
function actionDescription(a) {
    const routes = ["北路", "中路", "南路"];
    if (a.kind === "wait") return "维持当前部署";
    if (a.kind === "build") return `建造${NAMES[a.btype]} · 槽位 ${a.slot}`;
    if (a.kind === "tech") return "升级科技，解锁攻城车";
    if (a.kind === "produce") return `生产${NAMES[a.utype]}`;
    if (a.kind === "layout") return `调整建筑布局 · ${a.slot} ↔ ${a.slot_b}`;
    if (a.kind === "repair")
        return `维修${a.slot === null ? "总部" : "槽位 " + a.slot}`;
    if (a.kind === "deploy") return `${routes[a.route]}部署${NAMES[a.utype]}`;
    return `${a.kind === "signal" ? "信号集结" : "战略轰炸"} · 区域 ${a.region + 1}`;
}
function updateDecisions() {
    $("decisions").innerHTML = app.decisions
        .map(
            (d) =>
                `<div class="order ${d.side === "right" ? "red" : ""}"><b>${d.side === "right" ? "红" : "蓝"}方 · ${BOT_NAMES[d.bot]}</b><small>${PHASE[d.phase]} / ${(d.tick * 0.5).toFixed(1)}s</small>${actionDescription(d.action)}</div>`,
        )
        .join("");
}
function logMessage(text, tick) {
    const li = document.createElement("li"),
        time = document.createElement("time");
    time.textContent = (tick * 0.5).toFixed(1) + "s";
    li.append(time, document.createTextNode(text));
    $("events").prepend(li);
    while ($("events").children.length > 45)
        $("events").lastElementChild.remove();
}
function logEvent(event) {
    const team =
        event.player === undefined ? "" : event.player ? "红方" : "蓝方";
    let text;
    switch (event.type) {
        case "produce":
            text = `${team}生产 ${event.count} 个${NAMES[event.unit]}`;
            break;
        case "deploy":
            text = `${team}从${{ north: "北", mid: "中", south: "南" }[event.route]}路部署 ${event.count} 个${NAMES[event.unit]}`;
            break;
        case "tech":
            text = `${team}科技升级，解锁攻城车`;
            break;
        case "build":
            text = `${team}建造${NAMES[event.building]}`;
            break;
        case "layout":
            text = `${team}调整建筑布局`;
            break;
        case "repair":
            text = `${team}修复 ${event.healed} HP`;
            break;
        case "signal":
            text = `${team}发出信号，临时改变全军目标`;
            break;
        case "bomb_warning":
            text = `${team}标记轰炸区，两秒后落弹`;
            break;
        case "bomb":
            text = `${team}轰炸落下，命中 ${event.hit.length} 个目标`;
            break;
        case "building_destroyed":
            text = `${team}${NAMES[event.building]}被摧毁`;
            break;
        case "node_flip":
            text = `${team}取得${event.node === 0 ? "北" : "南"}节点`;
            break;
        case "income":
            text = `${team}获得 ${event.amount} 资源`;
            break;
        case "round_end":
            text = "本轮进攻结束，存活单位撤回基地";
            break;
        default:
            return;
    }
    logMessage(text, event.tick);
}
function showResult() {
    const state = app.terminal;
    if (!state) return;
    app.paused = true;
    $("result").hidden = false;
    const winner =
        state.winner < 0 ? "双方平局" : state.winner ? "红方获胜" : "蓝方获胜";
    $("result").textContent =
        `${winner} · ${state.end_reason === "hq_destroyed" ? "总部摧毁" : "六轮结束，按总部 HP + 节点时间评分"} · ${state.players.map((p) => p.score.toFixed(1)).join(" : ")}`;
    $("lesson").textContent = $("result").textContent;
    updateControls();
}
$("pause").onclick = () => {
    app.paused = !app.paused;
    updateControls();
};
$("step").onclick = async () => {
    app.paused = true;
    if (!app.queue.length) await requestStep();
    advanceFrame();
    app.fraction = 0;
    updateControls();
};
$("restart").onclick = newGame;
$("apply").onclick = newGame;
$("camera").onclick = () => scene?.resetCamera();
document.querySelectorAll("[data-speed]").forEach(
    (button) =>
        (button.onclick = () => {
            app.speed = Number(button.dataset.speed);
            document
                .querySelectorAll("[data-speed]")
                .forEach((b) => b.classList.toggle("active", b === button));
        }),
);
$("replay").onclick = () => {
    if (app.id) {
        const link = document.createElement("a");
        link.href = `/api/games/${app.id}/replay`;
        link.download = "replay.json";
        link.click();
    }
};
let lastTime = performance.now();
function loop(time) {
    const dt = Math.min(100, time - lastTime);
    lastTime = time;
    if (!app.paused) {
        app.animationTime += dt;
        if (app.queue.length) {
            app.fraction += dt / (500 / app.speed);
            while (app.fraction >= 1 && app.queue.length) {
                app.fraction -= 1;
                advanceFrame();
            }
        } else if (!app.terminal) requestStep();
    }
    scene?.draw(
        app.frame,
        app.previous,
        app.paused || !app.queue.length ? 1 : app.fraction,
        app.animationTime,
        app.selected,
        $("show-labels").checked,
    );
    requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
newGame();
