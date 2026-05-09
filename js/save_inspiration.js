import { app } from "../../scripts/app.js";
import {
    loadWorkflowConfig,
    findCheckpoint, extractPrompt, extractSamplerData, findLoras,
    getLastGeneratedImage, saveInspiration, showToast, esc
} from "/extensions/raccoon_utils/raccoon_utils.js";

// ── Extension ─────────────────────────────────────────────────────────

app.registerExtension({
    name: "RaccoonAI.SaveInspiration",
    async setup() { waitForMenu(); }
});

// ── Menu Button ───────────────────────────────────────────────────────

function waitForMenu() {
    const check = () => {
        if (document.getElementById("raccoon-save-btn")) return;
        const mgr = findManagerButton();
        if (mgr) { mgr.insertAdjacentElement("beforebegin", createButton()); return; }
        setTimeout(check, 600);
    };
    check();
    const obs = new MutationObserver(() => {
        if (document.getElementById("raccoon-save-btn")) { obs.disconnect(); return; }
        const mgr = findManagerButton();
        if (mgr) { mgr.insertAdjacentElement("beforebegin", createButton()); obs.disconnect(); }
    });
    obs.observe(document.body, { childList: true, subtree: true });
}

function findManagerButton() {
    for (const el of document.querySelectorAll("button, div[class*='btn'], div[class*='button']")) {
        if (el.textContent.includes("Manager") && el.offsetParent !== null) return el;
    }
    return null;
}

function createButton() {
    const btn = document.createElement("button");
    btn.id = "raccoon-save-btn";
    btn.title = "Salvar Inspiration no RaccoonAI";
    btn.style.cssText = `
        background:transparent;color:#cba6f7;border:1px solid #45475a;
        border-radius:6px;padding:4px 12px;font-size:13px;font-weight:600;
        cursor:pointer;display:inline-flex;align-items:center;gap:5px;
        transition:background 0.15s,border-color 0.15s;margin-left:6px;
    `;
    btn.innerHTML = `<span style="font-size:14px">🦝</span> Salvar Inspiration`;
    btn.addEventListener("mouseenter", () => { btn.style.background = "rgba(203,166,247,0.12)"; btn.style.borderColor = "#cba6f7"; });
    btn.addEventListener("mouseleave", () => { btn.style.background = "transparent"; btn.style.borderColor = "#45475a"; });
    btn.addEventListener("click", onSaveInspiration);
    return btn;
}

// ── Main Flow ─────────────────────────────────────────────────────────

async function onSaveInspiration() {
    const nodes  = app.graph._nodes;
    const config = await loadWorkflowConfig();

    const data = {
        checkpoint:     findCheckpoint(nodes, config),
        positivePrompt: extractPrompt(nodes, config, "positive"),
        negativePrompt: extractPrompt(nodes, config, "negative"),
        loras:          findLoras(nodes),
        ...extractSamplerData(nodes, config),
    };

    const title = await showDialog(data);
    if (title === null) return;

    let imageBlob = null;
    try { imageBlob = await getLastGeneratedImage(); }
    catch (e) { console.warn("[RaccoonAI] Imagem não encontrada:", e.message); }

    try {
        await saveInspiration(title, data, imageBlob);
        showToast(`"${title}" salva com sucesso!`, "success");
    } catch (e) {
        showToast("Erro: " + e.message, "error");
    }
}

// ── Dialog ────────────────────────────────────────────────────────────

function showDialog(data) {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.65);display:flex;align-items:center;justify-content:center;";

        const suggested = data.checkpoint
            ? data.checkpoint.replace(/\.(safetensors|ckpt|pt)$/i, "").replace(/[_-]/g, " ").trim()
            : new Date().toLocaleDateString("pt-BR");

        const loraPreview = data.loras?.length
            ? `<b style="color:#a6e3a1">LoRAs:</b> ${data.loras.map(l => `${l.name}${l.weight != null ? ` ×${l.weight}` : ""}`).join(", ")}<br>`
            : "";

        const box = document.createElement("div");
        box.style.cssText = "background:#1e1e2e;border:1px solid #45475a;border-radius:12px;padding:24px;width:500px;max-width:92vw;font-family:system-ui,sans-serif;color:#cdd6f4;";
        box.innerHTML = `
            <div style="font-size:15px;font-weight:700;color:#cba6f7;margin-bottom:14px">🦝 Salvar Inspiration</div>
            <div style="font-size:11px;color:#6c7086;line-height:1.7;margin-bottom:14px;background:#11111b;border-radius:6px;padding:8px 10px;">
                ${data.checkpoint ? `<b style="color:#89b4fa">Checkpoint:</b> ${esc(data.checkpoint)}<br>` : ""}
                ${loraPreview}
                ${data.sampler ? `<b style="color:#89dceb">Sampler:</b> ${esc(data.sampler)} / ${esc(data.scheduler || "—")} &nbsp;|&nbsp; Steps: ${esc(data.steps || "—")} &nbsp;|&nbsp; CFG: ${esc(data.cfg || "—")}<br>` : ""}
                ${data.seed ? `<b style="color:#f5c2e7">Seed:</b> ${esc(data.seed)}` : ""}
            </div>
            <label style="font-size:11px;color:#a6adc8;display:block;margin-bottom:5px">Título *</label>
            <input id="ri-title" type="text" value="${esc(suggested)}"
                style="width:100%;box-sizing:border-box;background:#11111b;border:1px solid #45475a;border-radius:6px;padding:8px 10px;color:#cdd6f4;font-size:13px;outline:none;"/>
            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
                <button id="ri-cancel" style="background:none;border:1px solid #45475a;border-radius:6px;padding:6px 16px;color:#a6adc8;cursor:pointer;font-size:13px">Cancelar</button>
                <button id="ri-confirm" style="background:#cba6f7;border:none;border-radius:6px;padding:6px 18px;color:#1e1e2e;cursor:pointer;font-size:13px;font-weight:700">Salvar</button>
            </div>`;

        overlay.appendChild(box);
        document.body.appendChild(overlay);

        const input = box.querySelector("#ri-title");
        input.focus(); input.select();
        const close = v => { overlay.remove(); resolve(v); };
        box.querySelector("#ri-cancel").addEventListener("click", () => close(null));
        box.querySelector("#ri-confirm").addEventListener("click", () => { const v = input.value.trim(); if (!v) { input.style.borderColor = "#f38ba8"; return; } close(v); });
        input.addEventListener("keydown", e => { if (e.key === "Enter") { const v = input.value.trim(); if (v) close(v); } if (e.key === "Escape") close(null); });
        overlay.addEventListener("click", e => { if (e.target === overlay) close(null); });
    });
}
