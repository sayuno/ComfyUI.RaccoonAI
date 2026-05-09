# ComfyUI.RaccoonAI

Custom nodes for [ComfyUI](https://github.com/comfyanonymous/ComfyUI) that integrate with the [RaccoonAI](https://github.com/sayuno/RaccoonAI) local AI management system.

## Features

### 🦝 Salvar Inspiration
Saves the current generation as an **Inspiration** in RaccoonAI with one click.

Automatically extracts from the workflow:
- Generated image (preview)
- Positive and negative prompts
- Checkpoint used
- LoRAs (supports Power Lora Loader and standard LoraLoader)
- Sampler parameters: steps, CFG, sampler, scheduler, denoise, seed

### 🎭 Salvar Personagem
Saves the current generation as a **Prompt Card** (character) in RaccoonAI with one click.

Extracts the positive prompt and optionally attaches the character face image (via face crop node in the workflow).

---

## Installation

### Option A — Git clone
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/sayuno/ComfyUI.RaccoonAI.git raccoon_utils
```

### Option B — Manual
Download and extract into `ComfyUI/custom_nodes/raccoon_utils/`.

Restart ComfyUI. Two buttons will appear in the top menu bar next to the Manager button.

---

## Requirements

- [RaccoonAI](https://github.com/sayuno/RaccoonAI) running on `http://localhost:6969`
- ComfyUI with a workflow that uses `CLIPTextEncode`, `KSampler`, and a checkpoint loader

---

## Workflow Configuration

By default the nodes auto-detect prompts, checkpoint and sampler from the graph. For multi-KSampler or complex workflows, use the **RaccoonConfig** node or add a `Note` titled `RACCOON_CONFIG` with a JSON body:

```json
{
  "checkpointNode": null,
  "positiveNode": null,
  "negativeNode": null,
  "ksamplerNode": null
}
```

You can also create named configs in `js/raccoon_config.json` and reference them with:
```json
{ "use": "MY WORKFLOW NAME" }
```

---

## Project Structure

```
raccoon_utils/
  js/
    raccoon_utils.js       # Shared utilities and API functions
    save_inspiration.js    # 🦝 Save Inspiration button
    save_character.js      # 🎭 Save Character button
    raccoon_config.json    # Named workflow configs
  __init__.py
```

---

## API

The `raccoon_utils.js` module exports reusable functions for other nodes:

| Function | Description |
|---|---|
| `loadWorkflowConfig()` | Reads RACCOON_CONFIG from graph or file |
| `findCheckpoint(nodes, config)` | Extracts checkpoint filename |
| `extractPrompt(nodes, config, field)` | Extracts positive or negative prompt |
| `extractSamplerData(nodes, config)` | Extracts KSampler parameters |
| `findLoras(nodes)` | Lists all active LoRAs with weights |
| `getLastGeneratedImage()` | Returns last output image as Blob |
| `getCharacterFaceImage(config)` | Returns character face crop as Blob |
| `saveInspiration(title, data, imageBlob)` | POST to `/api/inspirations` |
| `savePromptCard(name, tags, categoryId, imageBlob)` | POST to `/api/prompt-cards` |
| `blobToBase64(blob)` | Converts Blob to base64 data URL |
| `showToast(message, type)` | Shows overlay toast notification |
