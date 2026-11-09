import { app } from "../../scripts/app.js";

// Raccoon Active Tags: watches the graph and shows the DB tags of every active LoRA / model.
// Nothing here is interactive — the Raccoon Lora Importer and Power Lora Loader rows drive it.
// rgthree rows and the Importer change widget.value in place without firing callbacks, so the
// graph is polled through a cheap signature instead of hooking events.

const NODE_TYPE = "RaccoonActiveTags";
const POWER_LORA_TYPE = "Power Lora Loader (rgthree)";
const MODEL_WIDGET_BY_TYPE = {
    RaccoonCheckpointLoader: "ckpt_name",
    RaccoonDiffusionModelLoader: "model_name",
    CheckpointLoaderSimple: "ckpt_name",
    UNETLoader: "unet_name",
};
const POLL_MS = 750;
const DEBOUNCE_MS = 400;
const MODE_MUTED = 2;
const MODE_BYPASS = 4;
const CONFIG_URL = new URL("./raccoon_config.json", import.meta.url).href;
const DEFAULT_API = "http://localhost:6969";

// ── Settings (same _settings block the other Raccoon nodes use) ─────────────────────────────

async function loadSettings() {
    try {
        const res = await fetch(`${CONFIG_URL}?t=${Date.now()}`);
        if (!res.ok) return {};
        return (await res.json())["_settings"] ?? {};
    } catch {
        return {};
    }
}

function authHeaders(s) {
    if (s.apiKey) return { "X-Raccoon-Key": s.apiKey };
    if (s.apiToken) return { Authorization: `Bearer ${s.apiToken}` };
    return {};
}

// ── Graph scan ──────────────────────────────────────────────────────────────────────────────

function isActiveNode(node) {
    return node.mode !== MODE_MUTED && node.mode !== MODE_BYPASS;
}

function collectActive() {
    const loras = [];
    const checkpoints = [];
    for (const node of app.graph?._nodes ?? []) {
        if (!isActiveNode(node)) continue;
        if (node.type === POWER_LORA_TYPE) {
            for (const w of node.widgets ?? []) {
                const v = w?.value;
                if (v && typeof v === "object" && typeof v.lora === "string" && v.lora && v.lora !== "None" && v.on) {
                    loras.push({ path: v.lora, strength: Number(v.strength ?? 1) });
                }
            }
            continue;
        }
        const widgetName = MODEL_WIDGET_BY_TYPE[node.type];
        if (widgetName) {
            const v = node.widgets?.find(w => w.name === widgetName)?.value;
            if (typeof v === "string" && v && !checkpoints.includes(v)) checkpoints.push(v);
        }
    }
    return { loras, checkpoints };
}

function tagNodes() {
    return (app.graph?._nodes ?? []).filter(n => n.type === NODE_TYPE);
}

// ── Text building ───────────────────────────────────────────────────────────────────────────

function splitTags(text) {
    return String(text || "").split(/[,\n]/).map(t => t.trim()).filter(Boolean);
}

function joinUnique(lists) {
    const seen = new Set();
    const out = [];
    for (const list of lists) {
        for (const tag of splitTags(list)) {
            const key = tag.toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            out.push(tag);
        }
    }
    return out.join(", ");
}

function fileName(path) {
    return String(path).split(/[/\\]/).pop();
}

// ── Shared resolver (one request per change, all nodes show the same result) ────────────────

const state = {
    signature: null,
    pendingTimer: null,
    requestSeq: 0,
    result: null,     // { items: [...], positive, negative, at }
    offline: false,
    updating: false,
};

async function resolve(active) {
    const seq = ++state.requestSeq;
    state.updating = true;
    renderAll();

    if (active.loras.length === 0 && active.checkpoints.length === 0) {
        state.result = { items: [], positive: "", negative: "", at: new Date() };
        state.offline = false;
        state.updating = false;
        renderAll();
        return;
    }

    try {
        const s = await loadSettings();
        const base = (s.apiUrl || DEFAULT_API).replace(/\/$/, "");
        const res = await fetch(`${base}/api/model-tags/resolve`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders(s) },
            body: JSON.stringify(active),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (seq !== state.requestSeq) return; // a newer change already superseded this one

        const ckpts = (data.checkpoints ?? []).map(r => ({ ...r, kind: "model" }));
        const loras = (data.loras ?? []).map((r, i) => ({ ...r, kind: "lora", strength: active.loras[i]?.strength }));
        const items = [...ckpts, ...loras];
        const found = items.filter(i => i.found);
        state.result = {
            items,
            positive: joinUnique(found.map(i => i.positiveTags)),
            negative: joinUnique(found.map(i => i.negativeTags)),
            at: new Date(),
        };
        state.offline = false;
    } catch (err) {
        if (seq !== state.requestSeq) return;
        console.warn("[RaccoonAI] Active Tags: resolve failed", err);
        state.offline = true; // keep the last good result
    } finally {
        if (seq === state.requestSeq) {
            state.updating = false;
            renderAll();
        }
    }
}

function tick() {
    if (tagNodes().length === 0) return;
    const active = collectActive();
    const signature = JSON.stringify(active);
    if (signature === state.signature) return;
    state.signature = signature;
    clearTimeout(state.pendingTimer);
    state.pendingTimer = setTimeout(() => resolve(active), DEBOUNCE_MS);
}

// ── Rendering ───────────────────────────────────────────────────────────────────────────────

function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
}

function renderInto(container) {
    container.replaceChildren();
    const r = state.result;
    const list = el("div", "rat-list");

    if (!r) {
        list.append(el("div", "rat-muted", "Carregando…"));
    } else if (r.items.length === 0) {
        list.append(el("div", "rat-muted", "Nenhuma LoRA ativa"));
    } else {
        for (const item of r.items) {
            const block = el("div", "rat-item");
            if (!item.found) {
                block.append(el("div", "rat-warn", `⚠ ${fileName(item.path)} — não cadastrada no sistema`));
                list.append(block);
                continue;
            }
            const icon = item.kind === "model" ? "🧠" : "✅";
            const suffix = item.kind === "model" ? " (modelo)" : `   ${Number(item.strength ?? 1).toFixed(2)}`;
            const head = el("div", "rat-head", `${icon} ${item.name}${suffix}`);
            if (item.ambiguous) head.append(el("span", "rat-warn", "  ⚠ nome repetido, conferir"));
            block.append(head);
            if (item.positiveTags) block.append(el("div", "rat-pos", `+ ${item.positiveTags}`));
            if (item.negativeTags) block.append(el("div", "rat-neg", `− ${item.negativeTags}`));
            list.append(block);
        }
    }
    container.append(list);

    let footerText;
    let footerCls = "rat-footer";
    if (state.offline) {
        footerText = "API offline — tags não atualizadas";
        footerCls += " rat-offline";
    } else if (state.updating) {
        footerText = "Atualizando…";
    } else if (r) {
        const loraCount = r.items.filter(i => i.kind === "lora").length;
        const modelCount = r.items.filter(i => i.kind === "model").length;
        footerText = `Atualizado ${r.at.toLocaleTimeString("pt-BR")} · ${loraCount} LoRAs · ${modelCount} modelo(s)`;
    }
    if (footerText) container.append(el("div", footerCls, footerText));
}

function renderAll() {
    for (const node of tagNodes()) {
        if (node.__ratContainer) renderInto(node.__ratContainer);
        const r = state.result;
        if (r) {
            const pos = node.widgets?.find(w => w.name === "positive_text");
            const neg = node.widgets?.find(w => w.name === "negative_text");
            if (pos) pos.value = r.positive;
            if (neg) neg.value = r.negative;
        }
    }
    app.graph?.setDirtyCanvas(true, true);
}

function hideWidget(w) {
    if (!w) return;
    w.hidden = true;
    w.computeSize = () => [0, -4];
    for (const dom of [w.element, w.inputEl]) if (dom) dom.style.display = "none";
}

const STYLE = `
.rat-root { font: 12px/1.4 sans-serif; color: #ddd; overflow-y: auto; max-height: 420px; padding: 4px 6px; box-sizing: border-box; }
.rat-item { margin-bottom: 6px; }
.rat-head { font-weight: 600; }
.rat-pos { color: #86efac; padding-left: 14px; word-break: break-word; }
.rat-neg { color: #fca5a5; padding-left: 14px; word-break: break-word; }
.rat-warn { color: #fbbf24; }
.rat-muted { color: #888; }
.rat-footer { border-top: 1px solid #333; margin-top: 4px; padding-top: 3px; color: #888; font-size: 11px; }
.rat-offline { color: #f87171; }
`;

app.registerExtension({
    name: "RaccoonAI.ActiveTags",
    setup() {
        const style = document.createElement("style");
        style.textContent = STYLE;
        document.head.append(style);
        setInterval(tick, POLL_MS);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_TYPE) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);

            hideWidget(this.widgets?.find(w => w.name === "positive_text"));
            hideWidget(this.widgets?.find(w => w.name === "negative_text"));

            const container = el("div", "rat-root");
            this.__ratContainer = container;
            this.addDOMWidget("active_tags", "div", container, { serialize: false });
            if (!this.size || this.size[0] < 320) this.setSize([360, Math.max(this.size?.[1] ?? 0, 220)]);

            renderInto(container);
            state.signature = null; // force a resolve for the new node
        };
    },
});
