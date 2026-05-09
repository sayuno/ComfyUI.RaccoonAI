import { app } from "../../scripts/app.js";

export const RACCOON_API = "http://localhost:6969";
const CONFIG_URL = "/extensions/raccoon_utils/raccoon_config.json";

// ── Config ────────────────────────────────────────────────────────────

export async function loadWorkflowConfig() {
    // 1. Note "RACCOON_CONFIG" no workflow (override por workflow)
    const note = readNoteConfig();

    // Note pode referenciar um named config: { "use": "HENTAI IMAGE" }
    if (note?.use) {
        const file = await readFileConfig();
        return file[note.use] ?? file["_default"] ?? {};
    }
    if (note) return note;

    // 2. JSON file pelo nome do workflow
    const file = await readFileConfig();
    const name = getWorkflowName();
    if (name && file[name]) return file[name];

    // 3. _default
    return file["_default"] ?? {};
}

function readNoteConfig() {
    const nodes = app.graph._nodes;

    // Node customizado RaccoonConfig — lê conexões + extra JSON
    const cfgNode = nodes.find(n => n.type === "RaccoonConfig");
    if (cfgNode) {
        const result = {};

        // Segue cada input conectado para identificar o nó fonte
        const inp = cfgNode.inputs ?? [];
        const checkpointSrc       = inp[0]?.link ? followInputFromNode(cfgNode, 0) : null;
        const positiveSrc         = inp[1]?.link ? followInputFromNode(cfgNode, 1) : null;
        const negativeSrc         = inp[2]?.link ? followInputFromNode(cfgNode, 2) : null;
        const ksamplerSrc         = inp[3]?.link ? followInputFromNode(cfgNode, 3) : null;
        const ksamplerAdvancedSrc = inp[4]?.link ? followInputFromNode(cfgNode, 4) : null;

        if (checkpointSrc)       result.checkpointNode       = checkpointSrc;
        if (positiveSrc)         result.positiveNode         = positiveSrc;
        if (negativeSrc)         result.negativeNode         = negativeSrc;
        if (ksamplerSrc)         result.ksamplerNode         = ksamplerSrc;
        if (ksamplerAdvancedSrc) result.ksamplerAdvancedNode = ksamplerAdvancedSrc;

        // Merge com extra JSON (campo de texto do node)
        try {
            const extra = JSON.parse(cfgNode.widgets_values?.[0] ?? "{}");
            Object.assign(result, extra);
        } catch {}

        return result;
    }

    // Fallback: Note com título RACCOON_CONFIG
    for (const n of nodes) {
        if (n.type === "Note" && n.title === "RACCOON_CONFIG") {
            try { return JSON.parse(n.widgets_values?.[0] ?? "{}"); } catch {}
        }
    }
    return null;
}

function followInputFromNode(node, inputIndex) {
    const link = node.inputs?.[inputIndex]?.link;
    if (!link) return null;
    const ld = app.graph.links[link];
    if (!ld) return null;
    const src = app.graph.getNodeById(ld.origin_id);
    return resolveGetSet(src);
}

// Resolve cadeia GetNode → SetNode → fonte real
function resolveGetSet(node, depth = 0) {
    if (!node || depth > 10) return node;
    if (node.type === "GetNode") {
        const varName = node.widgets_values?.[0] ?? node.widgets?.[0]?.value;
        if (!varName) return node;
        const setNode = app.graph._nodes.find(n =>
            n.type === "SetNode" &&
            (n.widgets_values?.[0] === varName || n.widgets?.[0]?.value === varName)
        );
        if (setNode?.inputs?.[0]?.link) {
            const ld = app.graph.links[setNode.inputs[0].link];
            if (ld) return resolveGetSet(app.graph.getNodeById(ld.origin_id), depth + 1);
        }
    }
    return node;
}

async function readFileConfig() {
    try {
        const res = await fetch(`${CONFIG_URL}?t=${Date.now()}`);
        if (res.ok) return res.json();
    } catch {}
    return {};
}

function getWorkflowName() {
    if (app.graph?.extra?.title) return app.graph.extra.title;
    const t = document.title.replace(/\s*[-|]\s*ComfyUI\s*$/i, "").trim();
    return (t && t !== "ComfyUI") ? t : "";
}

// ── Node helpers ──────────────────────────────────────────────────────

export function followInput(node, inputIndex) {
    const link = node.inputs?.[inputIndex]?.link;
    if (!link) return null;
    const ld = app.graph.links[link];
    if (!ld) return null;
    return app.graph.getNodeById(ld.origin_id);
}

export function getClipText(node) {
    if (!node) return "";
    const byType = node.widgets?.find(w => w.type === "customtext");
    if (byType?.value) return byType.value;
    const byName = node.widgets?.find(w => w.name === "text");
    if (byName?.value) return byName.value;
    const byIdx = node.widgets?.[0]?.value;
    if (byIdx) return byIdx;
    const wv = node.widgets_values?.[0];
    return (typeof wv === "string" && wv.trim()) ? wv : "";
}

function isCheckpointFile(val) {
    return typeof val === "string" && /\.(safetensors|ckpt|gguf|pt)$/i.test(val);
}

function getNodeValue(node, index = 0) {
    // Lê valor ao vivo (widget interativo) primeiro, fallback para serializado
    return node?.widgets?.[index]?.value ?? node?.widgets_values?.[index];
}

// ── Checkpoint ────────────────────────────────────────────────────────

export function findCheckpoint(nodes, config) {
    // Nó conectado diretamente no RaccoonConfig
    if (config?.checkpointNode) {
        const val = getNodeValue(config.checkpointNode);
        if (isCheckpointFile(val)) return val;
    }
    // Strategy via JSON config
    const strategy = config?.checkpoint?.strategy;
    if (strategy && strategy !== "auto") {
        const r = applyNodeStrategy(nodes, config.checkpoint, isCheckpointFile);
        if (r) return r;
    }
    return findCheckpointAuto(nodes);
}

function findCheckpointAuto(nodes) {
    // 1. Checkpoint Selector — valor ao vivo (reflete mudança sem salvar)
    const sel = nodes.find(n => n.type === "Checkpoint Selector");
    const selVal = getNodeValue(sel);
    if (isCheckpointFile(selVal)) return selVal;

    // 2. Save Image w/Metadata modelname via conexão (não widget hardcoded)
    const saver = nodes.find(n => n.type === "Save Image w/Metadata");
    if (saver) {
        const modelIdx = saver.inputs?.findIndex(i => i.name === "modelname") ?? -1;
        if (modelIdx >= 0 && saver.inputs[modelIdx].link) {
            const src = followInput(saver, modelIdx);
            const val = src?.widgets_values?.[0];
            if (isCheckpointFile(val)) return val;
        }
        // widgets_values hardcoded = último recurso (pode estar desatualizado)
    }

    // 3. UnetLoaderGGUF
    const gguf = nodes.find(n => n.type === "UnetLoaderGGUF");
    const ggufVal = getNodeValue(gguf);
    if (isCheckpointFile(ggufVal)) return ggufVal;

    // 4. Standard loaders
    for (const [type, idx] of [["CheckpointLoaderSimple", 0], ["CheckpointLoader", 1]]) {
        const n = nodes.find(n => n.type === type);
        const v = getNodeValue(n, idx);
        if (isCheckpointFile(v)) return v;
    }

    // 5. Save Image w/Metadata widget hardcoded — último recurso
    const ckpt = saver?.widgets_values?.find(v => isCheckpointFile(v));
    if (ckpt) return ckpt;

    return null;
}

// ── Prompts ───────────────────────────────────────────────────────────

export function extractPrompt(nodes, config, field) {
    // Nó conectado diretamente no RaccoonConfig
    const nodeKey = field === "positive" ? "positiveNode" : "negativeNode";
    if (config?.[nodeKey]) {
        const t = getClipText(config[nodeKey]);
        if (t) return t;
    }
    // Strategy via JSON config
    const cfg = config?.[field];
    if (cfg?.strategy && cfg.strategy !== "auto") {
        const r = applyNodeStrategy(nodes, cfg, v => typeof v === "string" && v.trim().length > 0);
        if (r) return r;
    }
    return extractPromptAuto(nodes, field);
}

function extractPromptAuto(nodes, field) {
    const isNeg = field === "negative";
    const keyword = isNeg ? "NEG" : "POSITIVE";

    // Por título
    const byTitle = nodes.find(n =>
        n.type === "CLIPTextEncode" &&
        n.title?.toUpperCase().includes(keyword)
    );
    const t = getClipText(byTitle);
    if (t) return t;

    // Via KSampler
    const ks = nodes.find(n => n.type === "KSampler");
    if (ks) {
        const linked = followInput(ks, isNeg ? 2 : 1);
        if (linked?.type === "CLIPTextEncode") {
            const t2 = getClipText(linked);
            if (t2) return t2;
        }
    }

    // Qualquer CLIPTextEncode não-negativo/negativo
    for (const n of nodes.filter(n => n.type === "CLIPTextEncode")) {
        const hasNeg = n.title?.toUpperCase().includes("NEG");
        if (isNeg !== hasNeg) continue;
        const t3 = getClipText(n);
        if (t3) return t3;
    }
    return "";
}

// ── Sampler data ──────────────────────────────────────────────────────

export function extractSamplerData(nodes, config) {
    const result = {};

    // KSampler conectado → seed principal + parâmetros base
    if (config?.ksamplerNode) {
        const wv = config.ksamplerNode.widgets_values ?? [];
        // seed, control_after, steps, cfg, sampler_name, scheduler, denoise
        result.seed    = String(wv[0] ?? "");
        result.steps   = String(wv[2] ?? "");
        result.cfg     = String(wv[3] ?? "");
        result.sampler = wv[4] ?? null;
        result.scheduler = wv[5] ?? null;
        result.denoise = String(wv[6] ?? "");
    }

    // KSamplerAdvanced conectado → noise seed + parâmetros finais (sobrescreve se ambos conectados)
    if (config?.ksamplerAdvancedNode) {
        const wv = config.ksamplerAdvancedNode.widgets_values ?? [];
        // add_noise, noise_seed, control_after, steps, cfg, sampler_name, scheduler, start_at, end_at, return_noise
        result.noiseSeed = String(wv[1] ?? "");
        result.steps     = String(wv[3] ?? "");
        result.cfg       = String(wv[4] ?? "");
        result.sampler   = wv[5] ?? null;
        result.scheduler = wv[6] ?? null;
        result.denoise   = null;
    }

    if (Object.keys(result).length > 0) return result;

    const strategy = config?.sampler?.strategy ?? "auto";

    if (strategy === "ksampler_advanced") {
        const ks = nodes.find(n => n.type === "KSamplerAdvanced");
        if (ks) {
            const wv = ks.widgets_values ?? [];
            // add_noise, noise_seed, control_after, steps, cfg, sampler, scheduler, start_at, end_at, return_noise
            return { seed: String(wv[1] ?? ""), steps: String(wv[3] ?? ""), cfg: String(wv[4] ?? ""), sampler: wv[5] ?? null, scheduler: wv[6] ?? null, denoise: null };
        }
    }

    // auto / ksampler
    const ks = nodes.find(n => n.type === "KSampler");
    if (ks) {
        const wv = ks.widgets_values ?? [];
        // seed, control_after, steps, cfg, sampler, scheduler, denoise
        return { seed: String(wv[0] ?? ""), steps: String(wv[2] ?? ""), cfg: String(wv[3] ?? ""), sampler: wv[4] ?? null, scheduler: wv[5] ?? null, denoise: String(wv[6] ?? "") };
    }
    return {};
}

// ── LoRAs ─────────────────────────────────────────────────────────────

export function findLoras(nodes) {
    const loras = [];
    const seen = new Set();

    const power = nodes.find(n => n.type === "Power Lora Loader (rgthree)");
    if (power) {
        const sources = [...(power.widgets ?? []).map(w => w.value), ...(power.widgets_values ?? [])];
        for (const item of sources) {
            if (item && typeof item === "object" && typeof item.lora === "string" && item.lora && item.on !== false && !seen.has(item.lora)) {
                seen.add(item.lora);
                loras.push({ name: basename(item.lora), weight: item.strength ?? null });
            }
        }
        if (loras.length) return loras;
    }

    for (const node of nodes.filter(n => n.type === "LoraLoader")) {
        const name = node.widgets_values?.[0];
        if (typeof name === "string" && !seen.has(name)) {
            seen.add(name);
            loras.push({ name: basename(name), weight: node.widgets_values?.[1] ?? null });
        }
    }
    if (loras.length) return loras;

    for (const node of nodes.filter(n => n.type?.toLowerCase().includes("lora"))) {
        const vals = node.widgets_values ?? [];
        for (let i = 0; i < vals.length; i++) {
            const v = vals[i];
            if (typeof v === "string" && v.endsWith(".safetensors") && !seen.has(v)) {
                seen.add(v);
                loras.push({ name: basename(v), weight: typeof vals[i + 1] === "number" ? vals[i + 1] : null });
            }
        }
    }
    return loras;
}

// ── Images ────────────────────────────────────────────────────────────

export async function getLastGeneratedImage() {
    const allImages = await getAllHistoryImages();

    const outputImg = allImages.find(i => i.type === "output");
    if (outputImg) {
        const r = await fetch(viewUrl(outputImg));
        if (r.ok) return r.blob();
    }
    for (const img of allImages) {
        const r = await fetch(viewUrl(img));
        if (r.ok) return r.blob();
    }
    throw new Error("Nenhuma imagem encontrada na última geração");
}

export async function getCharacterFaceImage(config) {
    const allImages = await getAllHistoryImages();
    const prefix = config?.facePrefix ?? "raccoon_char_";

    // 1. Prefixo configurado
    const charImg = allImages.find(i => i.filename?.startsWith(prefix));
    if (charImg) {
        const r = await fetch(viewUrl(charImg));
        if (r.ok) return r.blob();
    }
    // 2. Último temp (PreviewImage do rosto — executa por último)
    const temps = allImages.filter(i => i.type === "temp");
    const last = temps[temps.length - 1];
    if (last) {
        const r = await fetch(viewUrl(last));
        if (r.ok) return r.blob();
    }
    throw new Error("Imagem do personagem não encontrada — gere uma imagem primeiro");
}

async function getAllHistoryImages() {
    const res = await fetch("/history?max_items=1");
    if (!res.ok) throw new Error(`History API retornou ${res.status}`);
    const history = await res.json();
    const promptId = Object.keys(history)[0];
    if (!promptId) throw new Error("Histórico vazio — gere uma imagem primeiro");
    const outputs = history[promptId]?.outputs ?? {};
    return Object.values(outputs).flatMap(o => o?.images ?? []);
}

function viewUrl(img) {
    return `/view?filename=${encodeURIComponent(img.filename)}&subfolder=${encodeURIComponent(img.subfolder ?? "")}&type=${img.type ?? "output"}`;
}

// ── Generic strategy resolver ─────────────────────────────────────────

function applyNodeStrategy(nodes, cfg, validate) {
    if (!cfg) return null;

    if (cfg.strategy === "node_type" || cfg.strategy === "node_title") {
        const n = nodes.find(n =>
            n.type === cfg.nodeType &&
            (!cfg.title || n.title === cfg.title)
        );
        const val = n?.widgets_values?.[cfg.widgetIndex ?? 0];
        if (!validate || validate(val)) return val ?? null;
    }

    if (cfg.strategy === "set_get") {
        const setNode = nodes.find(n => n.type === "SetNode" && n.widgets_values?.[0] === cfg.variable);
        if (setNode?.inputs?.[0]?.link) {
            const src = followInput(setNode, 0);
            const val = src?.widgets_values?.[0];
            if (!validate || validate(val)) return val ?? null;
        }
    }
    return null;
}

// ── Shared UI ─────────────────────────────────────────────────────────

export function showToast(message, type = "info") {
    const colors = { success: "#a6e3a1", error: "#f38ba8", info: "#cba6f7" };
    const bg     = { success: "#1e3a2e", error: "#3a1e1e", info: "#2a1e3e" };
    const t = document.createElement("div");
    t.style.cssText = `
        position:fixed;bottom:24px;right:24px;z-index:10000;
        background:${bg[type]};color:${colors[type]};
        border:1px solid ${colors[type]};border-radius:8px;
        padding:10px 18px;font-family:system-ui,sans-serif;font-size:13px;
        box-shadow:0 4px 20px rgba(0,0,0,0.5);transition:opacity 0.3s;max-width:380px;
    `;
    t.textContent = message;
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 300); }, 3500);
}

export function basename(path) { return path.split(/[/\\]/).pop() ?? path; }

export function esc(str) {
    return String(str ?? "")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── API helpers ───────────────────────────────────────────────────────

export function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload  = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

export async function saveInspiration(title, data, imageBlob) {
    const fd = new FormData();
    fd.append("title", title);
    if (data.checkpoint)     fd.append("checkpoint", data.checkpoint);
    if (data.positivePrompt) fd.append("prompt",     data.positivePrompt);
    if (data.negativePrompt) fd.append("negPrompt",  data.negativePrompt);
    if (data.steps)          fd.append("steps",      data.steps);
    if (data.cfg)            fd.append("cfgScale",   data.cfg);
    if (data.sampler)        fd.append("sampler",    data.sampler);
    if (data.scheduler)      fd.append("scheduler",  data.scheduler);
    if (data.denoise)        fd.append("denoise",    data.denoise);
    if (data.seed)           fd.append("seed",       data.seed);
    if (data.noiseSeed)      fd.append("noiseSeed",  data.noiseSeed);
    if (data.loras?.length)  fd.append("lorasJson",  JSON.stringify(data.loras.map(l => ({ name: l.name, weight: l.weight }))));
    if (imageBlob)           fd.append("image",      imageBlob, "preview.png");

    const res = await fetch(`${RACCOON_API}/api/inspirations`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text().catch(() => `HTTP ${res.status}`));
    return res.json();
}

export async function savePromptCard(name, tags, categoryId, imageBlob) {
    const body = { categoryId, name, tags };
    if (imageBlob) body.previewImage = await blobToBase64(imageBlob);

    const res = await fetch(`${RACCOON_API}/api/prompt-cards`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(body)
    });
    if (!res.ok) throw new Error(await res.text().catch(() => `HTTP ${res.status}`));
    return res.json();
}
