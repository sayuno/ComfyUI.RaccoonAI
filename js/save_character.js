import { app } from "../../scripts/app.js";
import {
    loadWorkflowConfig,
    extractPrompt, getCharacterFaceImage,
    savePromptCard, showToast, esc
} from "/extensions/raccoon_utils/raccoon_utils.js";

const CATEGORY_ID = 35;

// ── Extension ─────────────────────────────────────────────────────────

app.registerExtension({
    name: "RaccoonAI.SaveCharacter",
    async setup() { waitForMenu(); }
});

// ── Menu Button ───────────────────────────────────────────────────────

function waitForMenu() {
    const check = () => {
        if (document.getElementById("raccoon-char-btn")) return;
        const mgr = findManagerButton();
        if (mgr) { mgr.insertAdjacentElement("beforebegin", createButton()); return; }
        setTimeout(check, 600);
    };
    check();
    const obs = new MutationObserver(() => {
        if (document.getElementById("raccoon-char-btn")) { obs.disconnect(); return; }
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
    btn.id = "raccoon-char-btn";
    btn.title = "Salvar Personagem no RaccoonAI";
    btn.style.cssText = `
        background:transparent;color:#a6e3a1;border:1px solid #45475a;
        border-radius:6px;padding:4px 12px;font-size:13px;font-weight:600;
        cursor:pointer;display:inline-flex;align-items:center;gap:5px;
        transition:background 0.15s,border-color 0.15s;margin-left:6px;
    `;
    btn.innerHTML = `<span style="font-size:14px">🎭</span> Salvar Personagem`;
    btn.addEventListener("mouseenter", () => { btn.style.background = "rgba(166,227,161,0.12)"; btn.style.borderColor = "#a6e3a1"; });
    btn.addEventListener("mouseleave", () => { btn.style.background = "transparent"; btn.style.borderColor = "#45475a"; });
    btn.addEventListener("click", onSaveCharacter);
    return btn;
}

// ── Main Flow ─────────────────────────────────────────────────────────

async function onSaveCharacter() {
    const nodes  = app.graph._nodes;
    const config = await loadWorkflowConfig();

    const positivePrompt = extractPrompt(nodes, config, "positive");
    if (!positivePrompt.trim()) {
        showToast("Prompt positivo não encontrado. Verifique o RACCOON_CONFIG do workflow.", "error");
        return;
    }

    const name = await showDialog(positivePrompt);
    if (name === null) return;

    let imageBlob = null;
    try { imageBlob = await getCharacterFaceImage(config); }
    catch (e) { console.warn("[RaccoonAI] Imagem não encontrada:", e.message); }

    try {
        await savePromptCard(name, positivePrompt, CATEGORY_ID, imageBlob);
        showToast(`"${name}" salvo com sucesso!`, "success");
    } catch (e) {
        showToast("Erro: " + e.message, "error");
    }
}

// ── Dialog ────────────────────────────────────────────────────────────

function showDialog(positivePrompt) {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.65);display:flex;align-items:center;justify-content:center;";

        const preview = positivePrompt
            ? `<div style="font-size:11px;color:#6c7086;line-height:1.6;margin-bottom:14px;background:#11111b;border-radius:6px;padding:8px 10px;max-height:80px;overflow-y:auto;">
                   <b style="color:#a6e3a1">Tags:</b> ${esc(positivePrompt.slice(0, 300))}${positivePrompt.length > 300 ? "…" : ""}
               </div>` : "";

        const box = document.createElement("div");
        box.style.cssText = "background:#1e1e2e;border:1px solid #45475a;border-radius:12px;padding:24px;width:460px;max-width:92vw;font-family:system-ui,sans-serif;color:#cdd6f4;";
        box.innerHTML = `
            <div style="font-size:15px;font-weight:700;color:#a6e3a1;margin-bottom:14px">🎭 Salvar Personagem</div>
            ${preview}
            <label style="font-size:11px;color:#a6adc8;display:block;margin-bottom:5px">Nome do personagem *</label>
            <input id="sc-name" type="text" placeholder="Ex: Seriune, Sophia..."
                style="width:100%;box-sizing:border-box;background:#11111b;border:1px solid #45475a;border-radius:6px;padding:8px 10px;color:#cdd6f4;font-size:13px;outline:none;"/>
            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
                <button id="sc-cancel" style="background:none;border:1px solid #45475a;border-radius:6px;padding:6px 16px;color:#a6adc8;cursor:pointer;font-size:13px">Cancelar</button>
                <button id="sc-confirm" style="background:#a6e3a1;border:none;border-radius:6px;padding:6px 18px;color:#1e1e2e;cursor:pointer;font-size:13px;font-weight:700">Salvar</button>
            </div>`;

        overlay.appendChild(box);
        document.body.appendChild(overlay);

        const input = box.querySelector("#sc-name");
        input.focus();
        const close = v => { overlay.remove(); resolve(v); };
        box.querySelector("#sc-cancel").addEventListener("click", () => close(null));
        box.querySelector("#sc-confirm").addEventListener("click", () => { const v = input.value.trim(); if (!v) { input.style.borderColor = "#f38ba8"; return; } close(v); });
        input.addEventListener("keydown", e => { e.stopPropagation(); if (e.key === "Enter") { const v = input.value.trim(); if (v) close(v); } if (e.key === "Escape") close(null); });
        input.addEventListener("keyup",   e => e.stopPropagation());
        input.addEventListener("keypress", e => e.stopPropagation());
        overlay.addEventListener("click", e => { if (e.target === overlay) close(null); });
    });
}
