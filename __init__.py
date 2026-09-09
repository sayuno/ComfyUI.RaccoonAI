import os
import json
import re
import time
import folder_paths


class AnyType(str):
    def __ne__(self, other):
        return False


any_type = AnyType("*")


# --- Shared good-seed storage -------------------------------------------------

SEEDS_FILE = os.path.join(os.path.dirname(__file__), "good_seeds.json")


def load_good_seeds():
    if not os.path.exists(SEEDS_FILE):
        return []
    try:
        with open(SEEDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def build_seed_entry(seed, sampler_name, scheduler, steps, cfg, denoise, description, used_for):
    return {
        "seed": _to_int(seed),
        "sampler": (sampler_name or "").strip(),
        "scheduler": (scheduler or "").strip(),
        "steps": _to_int(steps),
        "cfg": _to_float(cfg),
        "denoise": _to_float(denoise, 1.0),
        "description": (description or "").strip(),
        "used_for": (used_for or "").strip(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def append_good_seed(entry):
    entries = load_good_seeds()
    entries.append(entry)
    try:
        with open(SEEDS_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"[RaccoonAI] saved seed {entry.get('seed')} ({len(entries)} total) -> {SEEDS_FILE}")
    except OSError as e:
        print(f"[RaccoonAI] FAILED to write {SEEDS_FILE}: {e}")
    return len(entries)


# --- Server route (header button posts here) ---------------------------------

try:
    from server import PromptServer
    from aiohttp import web

    @PromptServer.instance.routes.post("/raccoon/save_seed")
    async def _raccoon_save_seed(request):
        data = await request.json()
        entry = build_seed_entry(
            data.get("seed", 0),
            data.get("sampler_name", ""),
            data.get("scheduler", ""),
            data.get("steps", 0),
            data.get("cfg", 0),
            data.get("denoise", 1.0),
            data.get("description", ""),
            data.get("used_for", ""),
        )
        total = append_good_seed(entry)
        return web.json_response({"ok": True, "total": total, "seed": entry["seed"]})

    @PromptServer.instance.routes.get("/raccoon/good_seeds")
    async def _raccoon_list_seeds(request):
        return web.json_response(load_good_seeds())
except Exception as e:  # server/aiohttp unavailable (e.g. import outside ComfyUI)
    print(f"[RaccoonAI] save_seed route not registered: {e}")


# --- Nodes --------------------------------------------------------------------

class RaccoonConfig:
    """Workflow config node, now also able to save a good seed with one button.

    Connect the KSampler seed to the `seed` input, fill sampler_name/scheduler/
    steps/cfg/denoise to match the run, describe it in description/used_for, then
    click the 💾 Save this seed button (or flip save_seed on and queue). The entry
    is appended to good_seeds.json. save_seed stays off during normal runs, so the
    node never saves unless you ask it to.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "checkpoint":        (any_type,),
                "positive":          ("CONDITIONING",),
                "negative":          ("CONDITIONING",),
                "ksampler":          (any_type,),
                "ksampler_advanced": (any_type,),
            },
            "required": {
                "extra": ("STRING", {
                    "multiline": True,
                    "default": "{}",
                    "tooltip": "JSON opcional: { \"facePrefix\": \"raccoon_char_\" }"
                }),
                "seed":         ("INT",   {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "sampler_name": ("STRING", {"default": "euler"}),
                "scheduler":    ("STRING", {"default": "simple"}),
                "steps":        ("INT",   {"default": 8, "min": 1, "max": 10000}),
                "cfg":          ("FLOAT", {"default": 1.5, "min": 0.0, "max": 100.0, "step": 0.1}),
                "denoise":      ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "description":  ("STRING", {"multiline": True, "default": "", "tooltip": "What was generated (scene/character)"}),
                "used_for":     ("STRING", {"multiline": True, "default": "", "tooltip": "What this seed is good for (your note)"}),
                "save_seed":    ("BOOLEAN", {"default": False, "label_on": "save ✅", "label_off": "off"}),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "execute"
    CATEGORY = "RaccoonAI"
    OUTPUT_NODE = True

    def execute(self, extra, sampler_name="euler", scheduler="simple", steps=8, cfg=1.5,
                denoise=1.0, description="", used_for="", save_seed=False,
                checkpoint=None, positive=None, negative=None,
                ksampler=None, ksampler_advanced=None, seed=0):
        if save_seed:
            append_good_seed(build_seed_entry(seed, sampler_name, scheduler, steps, cfg, denoise, description, used_for))
        return {}


class StripExtension:
    @classmethod
    def INPUT_TYPES(cls):
        return { "required": { "filename": ("STRING", { "default": "" }) } }

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("name",)
    FUNCTION = "execute"
    CATEGORY = "RaccoonAI"

    def execute(self, filename):
        return (os.path.splitext(os.path.basename(filename))[0],)


class SaveGoodSeed:
    """Save a 'good' seed + KSampler config + notes to a JSON log with one toggle.

    Connect `seed` from the KSampler seed. Fill sampler/scheduler/steps/cfg/denoise
    to match the run, write what was generated in `description` and what it is for in
    `used_for`. Click the 💾 Save this seed button (or flip save on and queue): the
    entry is appended to good_seeds.json (next to this node).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed":         ("INT",   {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "sampler_name": ("STRING", {"default": "euler"}),
                "scheduler":    ("STRING", {"default": "simple"}),
                "steps":        ("INT",   {"default": 8, "min": 1, "max": 10000}),
                "cfg":          ("FLOAT", {"default": 1.5, "min": 0.0, "max": 100.0, "step": 0.1}),
                "denoise":      ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "description":  ("STRING", {"multiline": True, "default": "", "tooltip": "What was generated (scene/character)"}),
                "used_for":     ("STRING", {"multiline": True, "default": "", "tooltip": "What this seed is good for (your note)"}),
                "save":         ("BOOLEAN", {"default": False, "label_on": "save ✅", "label_off": "off"}),
            }
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("seed",)
    FUNCTION = "execute"
    CATEGORY = "RaccoonAI"
    OUTPUT_NODE = True

    def execute(self, seed, sampler_name, scheduler, steps, cfg, denoise, description, used_for, save):
        if save:
            append_good_seed(build_seed_entry(seed, sampler_name, scheduler, steps, cfg, denoise, description, used_for))
        return (seed,)


class ListGoodSeeds:
    """Read back saved good seeds from good_seeds.json and show them inside the node.

    `filter` matches (case-insensitive substring) against description, used_for and
    sampler. Empty = all. `limit` caps how many are shown. `newest_first` sorts by
    timestamp. The formatted list is shown read-only in the node and also output as
    STRING. Re-runs on every queue (IS_CHANGED) so it always reflects the latest file.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "filter":       ("STRING", {"default": "", "tooltip": "Search in description/used_for/sampler. Empty = all"}),
                "limit":        ("INT",   {"default": 20, "min": 1, "max": 1000}),
                "newest_first": ("BOOLEAN", {"default": True, "label_on": "newest first", "label_off": "oldest first"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "execute"
    CATEGORY = "RaccoonAI"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Always re-run so the list reflects the current file
        return float("nan")

    def _format(self, entries):
        if not entries:
            return "(no seeds saved yet)"
        lines = []
        for i, e in enumerate(entries, 1):
            lines.append(f"#{i}  seed {e.get('seed')}")
            lines.append(f"    {e.get('sampler','?')}/{e.get('scheduler','?')}  steps {e.get('steps','?')}  cfg {e.get('cfg','?')}  denoise {e.get('denoise','?')}")
            if e.get("description"):
                lines.append(f"    desc: {e['description']}")
            if e.get("used_for"):
                lines.append(f"    use:  {e['used_for']}")
            if e.get("timestamp"):
                lines.append(f"    {e['timestamp']}")
            lines.append("")
        return "\n".join(lines).rstrip()

    def execute(self, filter, limit, newest_first):
        entries = load_good_seeds()

        term = filter.strip().lower()
        if term:
            entries = [
                e for e in entries
                if term in str(e.get("description", "")).lower()
                or term in str(e.get("used_for", "")).lower()
                or term in str(e.get("sampler", "")).lower()
            ]

        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=newest_first)
        entries = entries[:limit]

        text = self._format(entries)
        return {"ui": {"text": [text]}, "result": (text,)}


def _slug(value, default="unknown"):
    """Filename-safe token: basename, no extension, only [A-Za-z0-9-]."""
    text = str(value if value is not None else "").strip()
    if not text:
        return default
    text = os.path.splitext(os.path.basename(text.replace("\\", "/")))[0]
    text = re.sub(r"[^A-Za-z0-9\-]+", "-", text).strip("-")
    return text or default


DEFAULT_OUTPUT_ROOT = "D:\\RaccoonAI\\output"


def _list_output_subfolders(base=DEFAULT_OUTPUT_ROOT):
    """Existing subfolders under the output root, for the `subfolder` combo.
    Rebuilt every time ComfyUI loads/refreshes node defs, so new folders show up
    after a page refresh without a server restart."""
    options = ["."]
    try:
        for name in sorted(os.listdir(base)):
            if not name.startswith(".") and os.path.isdir(os.path.join(base, name)):
                options.append(name)
    except OSError:
        pass
    return options


def _folder_from_model(model_name):
    """Last path segment before the filename, e.g. 'anime' from
    'image/sdxl/anime/0_Perfect_v8.safetensors'. None for a flat/root
    checkpoint (no subfolder in its name)."""
    if not model_name:
        return None
    parts = str(model_name).replace("\\", "/").split("/")
    return parts[-2] if len(parts) > 1 else None


def _resolve_save_folder(output_dir, subfolder, new_subfolder, auto_folder=None):
    """output_dir + (typed new_subfolder, else auto_folder from the model's own
    path, else picked subfolder, else root). `auto_folder` is what keeps the
    save location following whichever checkpoint group (anime/sdxl/krea/...)
    is actually wired in, instead of a `subfolder` picked once and forgotten."""
    folder = os.path.abspath(os.path.expandvars(str(output_dir).strip()))
    chosen = (new_subfolder or "").strip().strip("\\/")
    if not chosen and auto_folder:
        chosen = auto_folder
    if not chosen and subfolder and subfolder != ".":
        chosen = subfolder
    if chosen:
        folder = os.path.join(folder, chosen)
    os.makedirs(folder, exist_ok=True)
    return folder


class RaccoonSaveImage:
    """Save images as `model_sampler_scheduler_seed_YYYYmmDDHHMMSS.ext`.

    `output_dir` is required — the folder is created if missing. Every name token is
    sanitized (basename, extension stripped, only letters/digits/dash), so a model
    like `image\\sdxl\\0_Perfect_v8.safetensors` becomes `0-Perfect-v8`. When a batch has
    more than one image, `_00`, `_01`, ... is appended. Existing files are never
    overwritten — a `_1`, `_2` suffix is added instead. PNG saves keep the workflow in
    the metadata so the image can be dragged back into ComfyUI.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images":     ("IMAGE",),
                "output_dir": ("STRING", {"default": DEFAULT_OUTPUT_ROOT, "tooltip": "Base folder"}),
                "subfolder":  (_list_output_subfolders(), {"tooltip": "Existing subfolder under output_dir, or '.' for the base folder"}),
                "model":      (any_type, {"tooltip": "Any model name — Load Checkpoint, Load Diffusion Model, etc."}),
                "sampler_name": ("STRING", {"default": "euler", "forceInput": False}),
                "scheduler":    ("STRING", {"default": "simple", "forceInput": False}),
                "seed":         ("INT",   {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "extension":    (["png", "jpg", "webp"],),
                "quality":      ("INT",   {"default": 95, "min": 1, "max": 100, "tooltip": "jpg/webp only"}),
            },
            "optional": {
                "auto_subfolder": ("BOOLEAN", {"default": True, "label_on": "auto do checkpoint ✅", "label_off": "manual",
                                                "tooltip": "Save into a subfolder matching the checkpoint's own folder (e.g. anime/sdxl/krea) instead of a fixed one you have to remember to change"}),
                "new_subfolder": ("STRING", {"default": "", "tooltip": "Type a new subfolder name to create it (overrides everything else, including auto_subfolder)"}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("paths",)
    FUNCTION = "execute"
    CATEGORY = "RaccoonAI"
    OUTPUT_NODE = True

    def execute(self, images, output_dir, subfolder, model, sampler_name, scheduler, seed,
                extension, quality, auto_subfolder=True, new_subfolder="", prompt=None, extra_pnginfo=None):
        import numpy as np
        from PIL import Image

        auto_folder = _folder_from_model(model) if auto_subfolder else None
        folder = _resolve_save_folder(output_dir, subfolder, new_subfolder, auto_folder)

        stem = "_".join([
            _slug(model, "model"),
            _slug(sampler_name, "sampler"),
            _slug(scheduler, "scheduler"),
            str(_to_int(seed)),
            time.strftime("%Y%m%d%H%M%S"),
        ])

        pnginfo = None
        if extension == "png":
            from PIL.PngImagePlugin import PngInfo
            pnginfo = PngInfo()
            if prompt is not None:
                pnginfo.add_text("prompt", json.dumps(prompt))
            for key, value in (extra_pnginfo or {}).items():
                pnginfo.add_text(key, json.dumps(value))

        total = len(images)
        saved = []
        for index, tensor in enumerate(images):
            array = np.clip(255.0 * tensor.cpu().numpy(), 0, 255).astype(np.uint8)
            img = Image.fromarray(array)

            name = stem if total == 1 else f"{stem}_{index:02d}"
            path = os.path.join(folder, f"{name}.{extension}")
            dedupe = 1
            while os.path.exists(path):
                path = os.path.join(folder, f"{name}_{dedupe}.{extension}")
                dedupe += 1

            if extension == "png":
                img.save(path, pnginfo=pnginfo, compress_level=4)
            else:
                img.convert("RGB").save(path, quality=quality)

            saved.append(path)
            print(f"[RaccoonAI] saved {path}")

        return {"ui": {"text": ["\n".join(saved)]}, "result": ("\n".join(saved),)}


class RaccoonExtractVideoFrames:
    """Sample a video's frame batch (from `Get Video Components`) at a fixed time
    interval — supports fractional seconds (e.g. 0.2s = 5 frames/sec) — and save each
    sampled frame as a sequentially numbered image. Built for pulling spritesheet
    frames out of an I2V walk-cycle render: interval_seconds picks how far apart the
    poses are, independent of the video's actual fps.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images":           ("IMAGE", {"tooltip": "Full frame batch from Get Video Components"}),
                "fps":              ("FLOAT", {"default": 24.0, "min": 0.01, "max": 240.0, "step": 0.01, "forceInput": True}),
                "interval_seconds": ("FLOAT", {"default": 0.2, "min": 0.01, "max": 60.0, "step": 0.01,
                                                "tooltip": "Time between saved frames — fractional is fine (0.2 = 5 frames/sec)"}),
                "output_dir":       ("STRING", {"default": DEFAULT_OUTPUT_ROOT}),
                "subfolder":        (_list_output_subfolders(), {"tooltip": "Existing subfolder under output_dir, or '.' for the base folder"}),
                "prefix":           ("STRING", {"default": "frame"}),
                "extension":        (["png", "jpg", "webp"],),
            },
            "optional": {
                "new_subfolder": ("STRING", {"default": "", "tooltip": "Type a new subfolder name to create it"}),
                "max_frames":    ("INT", {"default": 0, "min": 0, "max": 999, "tooltip": "0 = no limit"}),
                "quality":       ("INT", {"default": 95, "min": 1, "max": 100, "tooltip": "jpg/webp only"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "INT")
    RETURN_NAMES = ("sampled_images", "paths", "count")
    FUNCTION = "execute"
    CATEGORY = "RaccoonAI"
    OUTPUT_NODE = True

    def execute(self, images, fps, interval_seconds, output_dir, subfolder, prefix, extension,
                new_subfolder="", max_frames=0, quality=95):
        import numpy as np
        import torch
        from PIL import Image

        total = len(images)
        step = max(1, round(fps * interval_seconds))
        indices = list(range(0, total, step))
        if max_frames and len(indices) > max_frames:
            indices = indices[:max_frames]

        folder = _resolve_save_folder(output_dir, subfolder, new_subfolder)
        stem = _slug(prefix, "frame")

        saved = []
        for order, frame_index in enumerate(indices):
            tensor = images[frame_index]
            array = np.clip(255.0 * tensor.cpu().numpy(), 0, 255).astype(np.uint8)
            img = Image.fromarray(array)

            name = f"{stem}_{order:03d}"
            path = os.path.join(folder, f"{name}.{extension}")
            dedupe = 1
            while os.path.exists(path):
                path = os.path.join(folder, f"{name}_{dedupe}.{extension}")
                dedupe += 1

            if extension == "png":
                img.save(path, compress_level=4)
            else:
                img.convert("RGB").save(path, quality=quality)

            saved.append(path)
            print(f"[RaccoonAI] extracted frame {frame_index}/{total} -> {path}")

        sampled = images[torch.tensor(indices, dtype=torch.long, device=images.device)] if indices else images[:0]
        return {"ui": {"text": ["\n".join(saved)]}, "result": (sampled, "\n".join(saved), len(saved))}


# --- Cached file hashing (AutoV2 / sha256[:10], A1111+Civitai convention) -----

HASH_CACHE_FILE = os.path.join(os.path.dirname(__file__), "hash_cache.json")


def _load_hash_cache():
    if not os.path.exists(HASH_CACHE_FILE):
        return {}
    try:
        with open(HASH_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_hash_cache(cache):
    try:
        with open(HASH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError as e:
        print(f"[RaccoonAI] FAILED to write {HASH_CACHE_FILE}: {e}")


def file_hash10(path):
    """sha256[:10] of a file, cached by (path, mtime, size) so big checkpoints
    aren't re-hashed on every single generation."""
    if not path or not os.path.exists(path):
        return ""
    import hashlib
    stat = os.stat(path)
    cache = _load_hash_cache()
    cached = cache.get(path)
    if cached and cached.get("mtime") == stat.st_mtime and cached.get("size") == stat.st_size:
        return cached["hash10"]

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    hash10 = h.hexdigest()[:10]

    cache[path] = {"mtime": stat.st_mtime, "size": stat.st_size, "hash10": hash10}
    _save_hash_cache(cache)
    return hash10


def _find_checkpoint_name(prompt_dict, node_id, depth=0):
    """Walk a MODEL-typed link backward through model-transform nodes (LoraLoader,
    Power Lora Loader, Reroute, ...) until hitting the loader that actually names
    the checkpoint/diffusion-model file, and return that literal filename.

    Lets `model` accept the raw MODEL tensor (instead of requiring a separate
    string wire) when the passed-in value isn't already a string."""
    if depth > 12 or not isinstance(prompt_dict, dict) or node_id is None:
        return None
    node = prompt_dict.get(str(node_id))
    if not isinstance(node, dict):
        return None
    inputs = node.get("inputs") or {}
    class_type = str(node.get("class_type", ""))

    if class_type == "CheckpointLoaderSimple":
        name = _resolve_literal(prompt_dict, inputs.get("ckpt_name"))
        return name if isinstance(name, str) else None
    if class_type in ("UNETLoader", "RaccoonDiffusionModelLoader"):
        name = _resolve_literal(prompt_dict, inputs.get("unet_name")) or _resolve_literal(prompt_dict, inputs.get("model_name"))
        return name if isinstance(name, str) else None
    if class_type == "RaccoonCheckpointLoader":
        name = _resolve_literal(prompt_dict, inputs.get("ckpt_name"))
        return name if isinstance(name, str) else None

    # Not a loader yet — follow the MODEL-carrying input back one more hop.
    # Reroute uses "input"; LoraLoader/Power Lora Loader/etc. use "model".
    link = inputs.get("model")
    if not isinstance(link, list):
        link = inputs.get("input")
    if not isinstance(link, list) or len(link) != 2:
        return None
    return _find_checkpoint_name(prompt_dict, link[0], depth + 1)


def resolve_model_path(name):
    """Find a checkpoint regardless of which ComfyUI folder it lives in
    (checkpoints, diffusion_models/unet — e.g. ZIT models)."""
    import folder_paths
    for folder in ("checkpoints", "diffusion_models", "unet"):
        try:
            path = folder_paths.get_full_path(folder, name)
        except Exception:
            path = None
        if path:
            return path
    return None


def resolve_lora_path(name):
    import folder_paths
    try:
        return folder_paths.get_full_path("loras", name)
    except Exception:
        return None


def _parse_loras(raw):
    """'name.safetensors:0.8' per line/comma -> [(name, weight), ...]"""
    entries = []
    for chunk in re.split(r"[\n,]+", raw or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, weight = chunk.partition(":")
        name = name.strip()
        if not name:
            continue
        entries.append((name, _to_float(weight.strip(), 1.0)))
    return entries


def _loras_from_prompt(prompt_dict):
    """Auto-discover enabled LoRAs + weights from any LoRA loader node found
    anywhere in the workflow graph -> [(name, weight), ...]. Supports the
    rgthree Power Lora Loader (multi-lora, on/off toggles) and the stock
    ComfyUI LoraLoader / LoraLoaderModelOnly nodes (one lora each).

    No wiring needed: `prompt` is the full API-format graph ComfyUI hands every
    node via the hidden PROMPT input, so this just reads it back out. Only
    literal widget values are picked up — a lora_name/strength converted to an
    input socket and fed from another node is a link (list), not a value, and
    is silently skipped."""
    entries = []
    if not isinstance(prompt_dict, dict):
        return entries
    for node in prompt_dict.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", ""))
        inputs = node.get("inputs") or {}

        if class_type.startswith("Power Lora Loader"):
            for key, value in inputs.items():
                if not key.lower().startswith("lora_") or not isinstance(value, dict):
                    continue
                if not value.get("on"):
                    continue
                name = value.get("lora")
                weight = _to_float(value.get("strength"), 1.0)
                if not name or weight == 0:
                    continue
                entries.append((name, weight))

        elif class_type == "DaSiWa_LTX2LoraLoader":
            # "DaSiWa Advanced LoRA Loader" — 10-slot stacker used in MiniMax H3 /
            # LTX-2.3 workflows. Slot rows live in the `stack_data` widget as a JSON
            # array: [{"on": bool, "lora": "name.safetensors", "str": 1.0, ...}, ...]
            stack_data = inputs.get("stack_data")
            if isinstance(stack_data, str):
                try:
                    rows = json.loads(stack_data)
                except (TypeError, json.JSONDecodeError):
                    rows = []
                for row in rows if isinstance(rows, list) else []:
                    if not isinstance(row, dict) or not row.get("on"):
                        continue
                    name = row.get("lora")
                    if not name or name == "None":
                        continue
                    weight = _to_float(row.get("str"), 1.0)
                    if weight == 0:
                        continue
                    entries.append((name, weight))

        elif class_type in ("LoraLoader", "LoraLoaderModelOnly"):
            name = inputs.get("lora_name")
            weight = inputs.get("strength_model", 1.0)
            if isinstance(name, str) and isinstance(weight, (int, float)) and weight != 0:
                entries.append((name, _to_float(weight, 1.0)))

    return entries


_SAMPLER_CLASS_TYPES = ("KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced")


def _follow(prompt_dict, link):
    """Resolve a [node_id, slot] link to the node dict it points at, or None."""
    if not isinstance(link, list) or len(link) != 2:
        return None
    node = prompt_dict.get(str(link[0]))
    return node if isinstance(node, dict) else None


def _resolve_literal(prompt_dict, value, depth=0):
    """Follow a link through pass-through nodes (Reroute, Primitive*) to the
    literal value at the end of the chain. Returns the value unchanged if it's
    already a literal (int/float/str/bool), or None if the chain dead-ends on
    something that isn't a simple pass-through (e.g. a real compute node)."""
    if depth > 12 or not isinstance(prompt_dict, dict):
        return value
    if not (isinstance(value, list) and len(value) == 2):
        return value
    node = prompt_dict.get(str(value[0]))
    if not isinstance(node, dict):
        return None
    inputs = node.get("inputs") or {}
    class_type = str(node.get("class_type", ""))
    if class_type == "Reroute":
        return _resolve_literal(prompt_dict, inputs.get("input"), depth + 1)
    if class_type.startswith("Primitive"):
        return _resolve_literal(prompt_dict, inputs.get("value"), depth + 1)
    return None


def _resolve_link_text(prompt_dict, link, depth=0):
    """Follow a prompt-graph link back to plain text, through passthrough
    (Reroute) and common text-encode nodes (CLIPTextEncode/-SDXL, Power Prompt).
    `link` is either a [node_id, slot] link or a literal already (in which
    case there's nothing to resolve)."""
    if depth > 8 or not isinstance(link, list) or len(link) != 2:
        return None
    node_id = link[0]
    node = prompt_dict.get(str(node_id))
    if not isinstance(node, dict):
        return None
    class_type = str(node.get("class_type", ""))
    inputs = node.get("inputs") or {}

    if class_type == "Reroute":
        return _resolve_link_text(prompt_dict, inputs.get("input"), depth + 1)

    if class_type.startswith("CLIPTextEncode"):
        parts, seen = [], set()
        for field in ("text_g", "text_l", "text"):
            value = inputs.get(field)
            if isinstance(value, str):
                value = value.strip()
            elif isinstance(value, list):
                value = _resolve_link_text(prompt_dict, value, depth + 1)
            else:
                value = None
            if value and value not in seen:
                seen.add(value)
                parts.append(value)
        return "\n".join(parts) if parts else None

    if class_type.startswith("Power Prompt"):
        value = inputs.get("prompt")
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return _resolve_link_text(prompt_dict, value, depth + 1)
        return None

    # Generic fallback: a plain Text/String primitive feeding this socket
    for key in ("text", "string", "value", "Text", "String"):
        value = inputs.get(key)
        if isinstance(value, str):
            return value
    return None


def _find_minimax_h3_info(prompt_dict):
    """Pull the assembled prompt text + duration/mode/resolution from a
    `MiniMaxH3Director` node ("DaSiWa MiniMax H3 Director"), if the workflow has
    one. The node's own text fields (`imd`/`soundscape`/`music` for T2VA/I2VA/
    FL2VA/L2VA, or the `ref` sub-dict's fields for REF2VA) live inside the
    `builder_state` widget as a JSON string -- not a plain STRING socket -- so
    they need to be parsed out rather than traced like a normal CLIPTextEncode.
    Returns {} if no MiniMaxH3Director node is found or builder_state is empty/
    unparseable; otherwise a dict with whichever of prompt/duration/mode/width/
    height/positive resolved.
    """
    if not isinstance(prompt_dict, dict):
        return {}
    for node in prompt_dict.values():
        if not isinstance(node, dict) or node.get("class_type") != "MiniMaxH3Director":
            continue
        inputs = node.get("inputs") or {}
        info = {}

        mode = inputs.get("mode")
        if isinstance(mode, str):
            info["mode"] = mode
        for key in ("duration", "width", "height"):
            value = inputs.get(key)
            if isinstance(value, (int, float)):
                info[key] = _to_int(value)

        builder_raw = inputs.get("builder_state")
        state = {}
        if isinstance(builder_raw, str) and builder_raw.strip():
            try:
                state = json.loads(builder_raw)
            except (TypeError, json.JSONDecodeError):
                state = {}
        if not isinstance(state, dict):
            state = {}

        if mode == "REF2VA":
            ref = state.get("ref") if isinstance(state.get("ref"), dict) else {}
            parts = []
            for label, key in (
                ("subject_definitions", "subject_definitions"), ("summary", "summary"),
                ("retention_analysis", "retention_analysis"), ("detailed_description", "detailed_description"),
                ("overall_soundscape", "soundscape"), ("non_diegetic_music", "music"),
            ):
                value = ref.get(key)
                if isinstance(value, str) and value.strip():
                    parts.append(f"{label}: {value.strip()}")
            if parts:
                info["prompt"] = "\n\n".join(parts)
        else:
            imd = state.get("imd")
            soundscape = state.get("soundscape")
            music = state.get("music")
            parts = []
            if isinstance(imd, str) and imd.strip():
                parts.append(f"integrated_multimodal_description: {imd.strip()}")
            if isinstance(soundscape, str) and soundscape.strip():
                parts.append(f"overall_soundscape: {soundscape.strip()}")
            if isinstance(music, str) and music.strip():
                parts.append(f"non_diegetic_music: {music.strip()}")
            if parts:
                info["prompt"] = "\n\n".join(parts)

        # T2VA / simple mode may carry the whole thing in the plain `prompt` widget
        # instead of builder_state -- fall back to it if the JSON parse gave nothing.
        if not info.get("prompt"):
            plain = inputs.get("prompt")
            if isinstance(plain, str) and plain.strip():
                info["prompt"] = plain.strip()

        if info:
            return info
    return {}


def _find_positive_negative_text(prompt_dict):
    """Auto-discover the actual positive/negative prompt text by tracing the
    sampler's `positive`/`negative` links back to their source node(s).

    SamplerCustomAdvanced (GUIDER-based: RandomNoise -> BasicGuider/CFGGuider ->
    BasicScheduler -> SamplerCustomAdvanced, used by MiniMax H3 and some Flux/Krea
    turbo workflows) doesn't take positive/negative directly -- they live on the
    guider node instead. BasicGuider only carries a single `conditioning` (no
    negative, typical of distilled/turbo samplers); CFGGuider carries both.

    If nothing resolves (e.g. the guider's conditioning comes from a
    MiniMaxH3Director's CONDITIONING output rather than a traceable
    CLIPTextEncode), fall back to the Director's own assembled prompt text via
    `_find_minimax_h3_info` -- MiniMax H3 has no separate negative, so that side
    stays empty.
    """
    if not isinstance(prompt_dict, dict):
        return "", ""
    for node in prompt_dict.values():
        if not isinstance(node, dict) or node.get("class_type") not in _SAMPLER_CLASS_TYPES:
            continue
        inputs = node.get("inputs") or {}

        if node.get("class_type") == "SamplerCustomAdvanced":
            guider_node = _follow(prompt_dict, inputs.get("guider"))
            g_inputs = (guider_node.get("inputs") or {}) if guider_node else {}
            positive = _resolve_link_text(prompt_dict, g_inputs.get("positive") or g_inputs.get("conditioning")) or ""
            negative = _resolve_link_text(prompt_dict, g_inputs.get("negative")) or ""
        else:
            positive = _resolve_link_text(prompt_dict, inputs.get("positive")) or ""
            negative = _resolve_link_text(prompt_dict, inputs.get("negative")) or ""

        if positive or negative:
            return positive, negative

    minimax_info = _find_minimax_h3_info(prompt_dict)
    if minimax_info.get("prompt"):
        return minimax_info["prompt"], ""
    return "", ""


def _sampler_config_from_advanced(prompt_dict, inputs):
    """SamplerCustomAdvanced doesn't hold seed/sampler/scheduler/cfg as its own
    widgets -- they live on its upstream RandomNoise / KSamplerSelect /
    BasicScheduler / (CFG)Guider nodes. Used by GUIDER-based workflows
    (MiniMax H3, some Flux/Krea turbo setups)."""
    config = {}

    noise_node = _follow(prompt_dict, inputs.get("noise"))
    if noise_node:
        seed = _resolve_literal(prompt_dict, (noise_node.get("inputs") or {}).get("noise_seed"))
        if isinstance(seed, (int, float)):
            config["seed"] = _to_int(seed)

    sampler_node = _follow(prompt_dict, inputs.get("sampler"))
    if sampler_node:
        sampler_name = _resolve_literal(prompt_dict, (sampler_node.get("inputs") or {}).get("sampler_name"))
        if isinstance(sampler_name, str):
            config["sampler_name"] = sampler_name

    sigmas_node = _follow(prompt_dict, inputs.get("sigmas"))
    if sigmas_node:
        s_inputs = sigmas_node.get("inputs") or {}
        scheduler = _resolve_literal(prompt_dict, s_inputs.get("scheduler"))
        if isinstance(scheduler, str):
            config["scheduler"] = scheduler
        steps = _resolve_literal(prompt_dict, s_inputs.get("steps"))
        if isinstance(steps, (int, float)):
            config["steps"] = _to_int(steps)

    guider_node = _follow(prompt_dict, inputs.get("guider"))
    if guider_node:
        cfg = _resolve_literal(prompt_dict, (guider_node.get("inputs") or {}).get("cfg"))
        if isinstance(cfg, (int, float)):
            config["cfg"] = _to_float(cfg)

    return config


def _find_sampler_config(prompt_dict):
    """Auto-discover seed/steps/cfg/sampler_name/scheduler from the actual
    sampler node used in the graph -> dict with whichever keys were resolved
    (literal widget values, not links)."""
    if not isinstance(prompt_dict, dict):
        return {}
    for node in prompt_dict.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs") or {}

        if class_type == "SamplerCustomAdvanced":
            config = _sampler_config_from_advanced(prompt_dict, inputs)
            if config:
                return config
            continue

        if class_type == "KSampler":
            seed_key = "seed"
        elif class_type == "KSamplerAdvanced":
            seed_key = "noise_seed"
        else:
            continue

        config = {}
        seed = inputs.get(seed_key)
        if isinstance(seed, (int, float)):
            config["seed"] = _to_int(seed)
        steps = inputs.get("steps")
        if isinstance(steps, (int, float)):
            config["steps"] = _to_int(steps)
        cfg = inputs.get("cfg")
        if isinstance(cfg, (int, float)):
            config["cfg"] = _to_float(cfg)
        sampler_name = inputs.get("sampler_name")
        if isinstance(sampler_name, str):
            config["sampler_name"] = sampler_name
        scheduler = inputs.get("scheduler")
        if isinstance(scheduler, str):
            config["scheduler"] = scheduler
        if config:
            return config
    return {}


def _merge_loras(auto_entries, manual_entries):
    """Union by lora name (case-insensitive); auto-discovered wins on overlap."""
    seen = {}
    for name, weight in auto_entries + manual_entries:
        key = name.lower()
        if key not in seen:
            seen[key] = (name, weight)
    return list(seen.values())


class RaccoonSaveImageMetadata:
    """Save images with full ComfyUI workflow embedded (drag back in) PLUS an
    A1111-style `parameters` text block so Civitai/other tools auto-detect the
    checkpoint and LoRAs used (resource auto-linking).

    - Model hash is sha256[:10], cached by file mtime/size — not recomputed every run.
    - `model` accepts any Load Checkpoint / Load Diffusion Model combo, including
      models that live in diffusion_models (e.g. ZIT), not just the checkpoints folder.
    - `loras` (optional): one `name:weight` per line/comma. Gets appended to the
      positive prompt as `<lora:name:weight>` and hashed into `Lora hashes:` so
      Civitai can link the resources.
    - width/height are read from the actual saved image, never entered by hand.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images":       ("IMAGE",),
                "output_dir":   ("STRING", {"default": DEFAULT_OUTPUT_ROOT, "tooltip": "Base folder"}),
                "subfolder":    (_list_output_subfolders(), {"tooltip": "Existing subfolder under output_dir, or '.' for the base folder"}),
                "model":        (any_type, {"tooltip": "Any model name — Load Checkpoint, Load Diffusion Model, etc."}),
                "sampler_name": ("STRING", {"default": "euler"}),
                "scheduler":    ("STRING", {"default": "simple"}),
                "steps":        ("INT",   {"default": 20, "min": 1, "max": 10000}),
                "cfg":          ("FLOAT", {"default": 7.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "seed":         ("INT",   {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "extension":    (["png", "jpg", "webp"],),
                "quality":      ("INT",   {"default": 95, "min": 1, "max": 100, "tooltip": "jpg/webp only"}),
            },
            "optional": {
                "auto_sampler_config": ("BOOLEAN", {"default": True, "label_on": "auto from KSampler ✅", "label_off": "manual widgets",
                                                     "tooltip": "Pull seed/steps/cfg/sampler/scheduler straight from the KSampler node in the graph"}),
                "positive": ("STRING", {"multiline": True, "default": "", "forceInput": True}),
                "negative": ("STRING", {"multiline": True, "default": "", "forceInput": True}),
                "loras":    ("STRING", {"multiline": True, "default": "", "forceInput": True, "tooltip": "name.safetensors:weight, one per line"}),
                "dasiwa_metadata": ("STRING", {"multiline": True, "default": "", "forceInput": True,
                                                "tooltip": "Optional: wire in DaSiWa Metadata Image Saver's `metadata` output (already a full A1111 'parameters' string) to use it as-is instead of Raccoon's own auto-detected positive/negative/sampler — for workflows (e.g. MiniMax H3) where Raccoon's graph-tracing can't find the right nodes"}),
                "auto_subfolder": ("BOOLEAN", {"default": True, "label_on": "auto do checkpoint ✅", "label_off": "manual",
                                                "tooltip": "Save into a subfolder matching the checkpoint's own folder (e.g. anime/sdxl/krea) instead of a fixed one you have to remember to change"}),
                "new_subfolder": ("STRING", {"default": "", "tooltip": "Type a new subfolder name to create it (overrides everything else, including auto_subfolder)"}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO", "unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("paths",)
    FUNCTION = "execute"
    CATEGORY = "RaccoonAI"
    OUTPUT_NODE = True

    def execute(self, images, output_dir, subfolder, model, sampler_name, scheduler, steps, cfg,
                seed, extension, quality, auto_sampler_config=True, positive="", negative="", loras="",
                dasiwa_metadata="", auto_subfolder=True, new_subfolder="", prompt=None, extra_pnginfo=None,
                unique_id=None):
        import numpy as np
        from PIL import Image

        if not isinstance(model, str):
            # `model` accepts any_type so a raw MODEL tensor can be wired in
            # directly — trace back through the graph to the actual loader
            # instead of stringifying the tensor object into garbage.
            model = _find_checkpoint_name(prompt, unique_id) or ""

        if auto_sampler_config:
            auto_cfg = _find_sampler_config(prompt)
            sampler_name = auto_cfg.get("sampler_name", sampler_name)
            scheduler = auto_cfg.get("scheduler", scheduler)
            steps = auto_cfg.get("steps", steps)
            cfg = auto_cfg.get("cfg", cfg)
            seed = auto_cfg.get("seed", seed)

        auto_folder = _folder_from_model(model) if auto_subfolder else None
        folder = _resolve_save_folder(output_dir, subfolder, new_subfolder, auto_folder)

        model_path = resolve_model_path(model)
        model_hash = file_hash10(model_path)
        model_name = _slug(model, "model")

        lora_entries = _merge_loras(_loras_from_prompt(prompt), _parse_loras(loras))
        lora_tags, lora_hash_parts = [], []
        for name, weight in lora_entries:
            lora_slug = _slug(name, name)
            lora_tags.append(f"<lora:{lora_slug}:{weight}>")
            lora_hash = file_hash10(resolve_lora_path(name))
            if lora_hash:
                lora_hash_parts.append(f"{lora_slug}: {lora_hash}")

        auto_positive, auto_negative = _find_positive_negative_text(prompt)
        positive_full = (positive or auto_positive or "").strip()
        if lora_tags:
            positive_full = (positive_full + " " + " ".join(lora_tags)).strip()

        stem = "_".join([
            model_name,
            _slug(sampler_name, "sampler"),
            _slug(scheduler, "scheduler"),
            str(_to_int(seed)),
            time.strftime("%Y%m%d%H%M%S"),
        ])

        total = len(images)
        saved = []
        for index, tensor in enumerate(images):
            array = np.clip(255.0 * tensor.cpu().numpy(), 0, 255).astype(np.uint8)
            img = Image.fromarray(array)
            if extension != "png":
                img = img.convert("RGB")
            width, height = img.width, img.height

            if dasiwa_metadata.strip():
                # Already a complete A1111 'parameters' string (DaSiWa built it from its own
                # metadata_config graph) — use verbatim, skip Raccoon's own auto-detection.
                parameters = dasiwa_metadata.strip()
            else:
                parameters = (
                    f"{positive_full}\n"
                    f"Negative prompt: {(negative or auto_negative or '').strip()}\n"
                    f"Steps: {_to_int(steps)}, Sampler: {sampler_name}, Schedule type: {scheduler}, "
                    f"CFG scale: {cfg}, Seed: {_to_int(seed)}, Size: {width}x{height}, "
                    f"Model hash: {model_hash}, Model: {model_name}"
                )
                if lora_hash_parts:
                    parameters += f', Lora hashes: "{", ".join(lora_hash_parts)}"'
                parameters += ", Version: RaccoonAI ComfyUI"

            name = stem if total == 1 else f"{stem}_{index:02d}"
            path = os.path.join(folder, f"{name}.{extension}")
            dedupe = 1
            while os.path.exists(path):
                path = os.path.join(folder, f"{name}_{dedupe}.{extension}")
                dedupe += 1

            if extension == "png":
                from PIL.PngImagePlugin import PngInfo
                pnginfo = PngInfo()
                pnginfo.add_text("parameters", parameters)
                if prompt is not None:
                    pnginfo.add_text("prompt", json.dumps(prompt))
                for key, value in (extra_pnginfo or {}).items():
                    pnginfo.add_text(key, json.dumps(value))
                img.save(path, pnginfo=pnginfo, compress_level=4)
            else:
                img.save(path, quality=quality)

            saved.append(path)
            print(f"[RaccoonAI] saved {path}")

        return {"ui": {"text": ["\n".join(saved)]}, "result": ("\n".join(saved),)}


def _ffmpeg_escape(value):
    """Escape a value for the ffmetadata file format (same rule ffmpeg/VHS use)."""
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;")
    value = value.replace("#", "\\#")
    value = value.replace("=", "\\=")
    value = value.replace("\n", "\\\n")
    return value


def _resolve_ffmpeg():
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        path = get_ffmpeg_exe()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    import shutil
    return shutil.which("ffmpeg")


class RaccoonSaveVideoMetadata:
    """Remux an already-encoded video (e.g. the Filenames output of
    VHS_VideoCombine) with the same Civitai/A1111-style `comment` metadata as
    RaccoonSaveImageMetadata, plus the full ComfyUI workflow for drag-back-in.

    Stream copy only (`-codec copy`) — no re-encode, no quality loss, just
    rewrites the container metadata. Resolution/frame count/fps are probed
    from the actual video file, never entered by hand.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path":   ("STRING", {"default": "", "forceInput": True, "tooltip": "Path to the already-encoded video (e.g. VHS_VideoCombine Filenames output)"}),
                "output_dir":   ("STRING", {"default": DEFAULT_OUTPUT_ROOT, "tooltip": "Base folder"}),
                "subfolder":    (_list_output_subfolders(), {"tooltip": "Existing subfolder under output_dir, or '.' for the base folder"}),
                "model":        (any_type, {"tooltip": "Any model name — Load Checkpoint, Load Diffusion Model, etc."}),
                "sampler_name": ("STRING", {"default": "euler"}),
                "scheduler":    ("STRING", {"default": "simple"}),
                "steps":        ("INT",   {"default": 20, "min": 1, "max": 10000}),
                "cfg":          ("FLOAT", {"default": 7.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "seed":         ("INT",   {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                "auto_sampler_config": ("BOOLEAN", {"default": True, "label_on": "auto from KSampler ✅", "label_off": "manual widgets",
                                                     "tooltip": "Pull seed/steps/cfg/sampler/scheduler straight from the KSampler node in the graph"}),
                "positive": ("STRING", {"multiline": True, "default": "", "forceInput": True}),
                "negative": ("STRING", {"multiline": True, "default": "", "forceInput": True}),
                "loras":    ("STRING", {"multiline": True, "default": "", "tooltip": "name.safetensors:weight, one per line"}),
                "auto_subfolder": ("BOOLEAN", {"default": True, "label_on": "auto do checkpoint ✅", "label_off": "manual",
                                                "tooltip": "Save into a subfolder matching the checkpoint's own folder (e.g. anime/sdxl/krea) instead of a fixed one you have to remember to change"}),
                "new_subfolder": ("STRING", {"default": "", "tooltip": "Type a new subfolder name to create it (overrides everything else, including auto_subfolder)"}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("path",)
    FUNCTION = "execute"
    CATEGORY = "RaccoonAI"
    OUTPUT_NODE = True

    def execute(self, video_path, output_dir, subfolder, model, sampler_name, scheduler, steps, cfg,
                seed, auto_sampler_config=True, positive="", negative="", loras="", auto_subfolder=True,
                new_subfolder="", prompt=None, extra_pnginfo=None):
        import subprocess

        if auto_sampler_config:
            auto_cfg = _find_sampler_config(prompt)
            sampler_name = auto_cfg.get("sampler_name", sampler_name)
            scheduler = auto_cfg.get("scheduler", scheduler)
            steps = auto_cfg.get("steps", steps)
            cfg = auto_cfg.get("cfg", cfg)
            seed = auto_cfg.get("seed", seed)

        video_path = str(video_path).strip()
        if not video_path or not os.path.exists(video_path):
            print(f"[RaccoonAI] video not found: {video_path}")
            return {"ui": {"text": [""]}, "result": ("",)}

        ffmpeg = _resolve_ffmpeg()
        if not ffmpeg:
            print("[RaccoonAI] ffmpeg not found, cannot write video metadata")
            return {"ui": {"text": [video_path]}, "result": (video_path,)}

        width = height = frame_count = 0
        fps = 0.0
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
        except Exception as e:
            print(f"[RaccoonAI] could not probe video: {e}")

        model_path = resolve_model_path(model)
        model_hash = file_hash10(model_path)
        model_name = _slug(model, "model")

        lora_entries = _merge_loras(_loras_from_prompt(prompt), _parse_loras(loras))
        lora_tags, lora_hash_parts = [], []
        for name, weight in lora_entries:
            lora_slug = _slug(name, name)
            lora_tags.append(f"<lora:{lora_slug}:{weight}>")
            lora_hash = file_hash10(resolve_lora_path(name))
            if lora_hash:
                lora_hash_parts.append(f"{lora_slug}: {lora_hash}")

        auto_positive, auto_negative = _find_positive_negative_text(prompt)
        positive_full = (positive or auto_positive or "").strip()
        if lora_tags:
            positive_full = (positive_full + " " + " ".join(lora_tags)).strip()

        minimax_info = _find_minimax_h3_info(prompt)

        parameters = (
            f"{positive_full}\n"
            f"Negative prompt: {(negative or auto_negative or '').strip()}\n"
            f"Steps: {_to_int(steps)}, Sampler: {sampler_name}, Schedule type: {scheduler}, "
            f"CFG scale: {cfg}, Seed: {_to_int(seed)}, Size: {width}x{height}, "
            f"Frames: {frame_count}, FPS: {fps:.3f}, "
            f"Model hash: {model_hash}, Model: {model_name}"
        )
        if lora_hash_parts:
            parameters += f', Lora hashes: "{", ".join(lora_hash_parts)}"'
        if minimax_info.get("mode"):
            parameters += f', MiniMax mode: {minimax_info["mode"]}'
        if minimax_info.get("duration"):
            parameters += f', MiniMax duration: {minimax_info["duration"]}s'
        parameters += ", Version: RaccoonAI ComfyUI"

        auto_folder = _folder_from_model(model) if auto_subfolder else None
        folder = _resolve_save_folder(output_dir, subfolder, new_subfolder, auto_folder)

        ext = os.path.splitext(video_path)[1].lstrip(".") or "mp4"
        stem = "_".join([
            model_name,
            _slug(sampler_name, "sampler"),
            _slug(scheduler, "scheduler"),
            str(_to_int(seed)),
            time.strftime("%Y%m%d%H%M%S"),
        ])
        dest = os.path.join(folder, f"{stem}.{ext}")
        dedupe = 1
        while os.path.exists(dest):
            dest = os.path.join(folder, f"{stem}_{dedupe}.{ext}")
            dedupe += 1

        meta_lines = [";FFMETADATA1", f"comment={_ffmpeg_escape(parameters)}"]
        if prompt is not None:
            meta_lines.append(f"comfy_prompt={_ffmpeg_escape(json.dumps(prompt))}")
        for key, value in (extra_pnginfo or {}).items():
            meta_lines.append(f"{_ffmpeg_escape(str(key))}={_ffmpeg_escape(json.dumps(value))}")

        meta_path = os.path.join(folder, f".{stem}.ffmeta.txt")
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write("\n".join(meta_lines) + "\n")

        cmd = [ffmpeg, "-y", "-i", video_path, "-i", meta_path,
               "-map", "0", "-map_metadata", "1", "-codec", "copy", dest]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[RaccoonAI] ffmpeg metadata mux failed: {result.stderr[-2000:]}")
                dest = video_path  # fall back: keep the original, unmodified file
        finally:
            try:
                os.remove(meta_path)
            except OSError:
                pass

        print(f"[RaccoonAI] saved {dest}")
        return {"ui": {"text": [dest]}, "result": (dest,)}


# --- Folder-aware selectors -----------------------------------------------------
#
# Modeled on comfy-image-saver's "Checkpoint Selector": a pure picker, no
# MODEL/CLIP/VAE output, just the filename string. Wire that one output into
# both the real loader (CheckpointLoaderSimple/UNETLoader) AND
# RaccoonSaveImageMetadata/RaccoonSaveVideoMetadata's `model` input, so they
# can never drift out of sync with each other.
#
# `folder` is a free-text field (type it, change it anytime) that live-filters
# the file dropdown to that subfolder — client-side, in
# js/raccoon_checkpoint_loader.js, which already has the full option list in
# the widget and just slices it on `folder` change. No server round-trip, and
# an unmatched/empty folder falls back to the full list instead of going empty.

class RaccoonCheckpointLoader:
    """Checkpoint Selector with a `folder` field you type/change to jump
    straight to that subfolder (models/checkpoints/<folder>/...) instead of
    hunting a 49+-item flat dropdown. Outputs just the filename (like the
    stock Checkpoint Selector) -- wire it into a CheckpointLoaderSimple AND
    into the Save Metadata node's `model` input so both stay in sync."""

    CATEGORY = "RaccoonAI"
    RETURN_TYPES = (folder_paths.get_filename_list("checkpoints"),)
    RETURN_NAMES = ("ckpt_name",)
    FUNCTION = "get_name"

    @classmethod
    def INPUT_TYPES(cls):
        names = folder_paths.get_filename_list("checkpoints")
        return {
            "required": {
                "folder": ("STRING", {"default": "", "tooltip": "Subfolder under models/checkpoints/ to filter to, e.g. anima. Empty = show everything."}),
                "ckpt_name": (names,),
            }
        }

    def get_name(self, folder, ckpt_name):
        return (ckpt_name,)


class RaccoonDiffusionModelLoader:
    """Same as Raccoon Checkpoint Loader but for models/diffusion_models
    (UNETLoader-style) -- Anima, Krea2, MiniMax H3, ZIT and anything else that
    loads via UNETLoader instead of a checkpoint. Outputs just the filename --
    wire it into UNETLoader AND the Save Metadata node's `model` input."""

    CATEGORY = "RaccoonAI"
    RETURN_TYPES = (folder_paths.get_filename_list("diffusion_models"),)
    RETURN_NAMES = ("model_name",)
    FUNCTION = "get_name"

    @classmethod
    def INPUT_TYPES(cls):
        names = folder_paths.get_filename_list("diffusion_models")
        return {
            "required": {
                "folder": ("STRING", {"default": "", "tooltip": "Subfolder under models/diffusion_models/ to filter to, e.g. anima. Empty = show everything."}),
                "model_name": (names,),
            }
        }

    def get_name(self, folder, model_name):
        return (model_name,)


class RaccoonLoraImporter:
    """Paste a LoRA list from /models/ideas into `paste_list`, one per line, click Importar: applies
    it to every "Power Lora Loader (rgthree)" node in the current graph. Two line shapes:
    `path/name.safetensors` (from "Copiar safetensors") matches by FULL PATH — needed because two
    LoRAs can share a filename in different folders, and only the path tells them apart; a bare
    `name.safetensors` (from "Copiar tudo", tags after `:` ignored) matches by basename like before.
    Either shape can end in `:peso` (e.g. `...Nipple_Penetration.safetensors:1.4`) to also set that
    row's strength — add it by hand, nothing copies a weight automatically yet. Matches turn ON,
    everything else turns OFF (clean combo, no leftover from a previous idea) — then redraws.

    All the real work happens client-side (js/raccoon_lora_importer.js) — a Python node can't reach
    another node's live widgets. This class only exists so the JS extension has a node type to hook
    the button onto, `paste_list` to read, and a place to show the last apply's result log. Never
    actually queued/executed as part of generation.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "paste_list": ("STRING", {
                    "multiline": True, "default": "",
                    "tooltip": "Cole aqui: path/nome.safetensors (ou nome.safetensors) por linha, opcionalmente :peso no final (ex: ...Nipple_Penetration.safetensors:1.4). Vem do botão 'Copiar tudo' ou 'Copiar safetensors' em /models/ideas."
                }),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "noop"
    CATEGORY = "RaccoonAI"
    OUTPUT_NODE = True

    def noop(self, paste_list):
        return {}


NODE_CLASS_MAPPINGS        = { "RaccoonConfig": RaccoonConfig, "StripExtension": StripExtension, "SaveGoodSeed": SaveGoodSeed, "ListGoodSeeds": ListGoodSeeds, "RaccoonSaveImage": RaccoonSaveImage, "RaccoonExtractVideoFrames": RaccoonExtractVideoFrames, "RaccoonSaveImageMetadata": RaccoonSaveImageMetadata, "RaccoonSaveVideoMetadata": RaccoonSaveVideoMetadata, "RaccoonCheckpointLoader": RaccoonCheckpointLoader, "RaccoonDiffusionModelLoader": RaccoonDiffusionModelLoader, "RaccoonLoraImporter": RaccoonLoraImporter }
NODE_DISPLAY_NAME_MAPPINGS = { "RaccoonConfig": "Raccoon Config 🦝", "StripExtension": "Strip Extension 🦝", "SaveGoodSeed": "Save Good Seed 🦝", "ListGoodSeeds": "List Good Seeds 🦝", "RaccoonSaveImage": "Raccoon Save Image 🦝", "RaccoonExtractVideoFrames": "Raccoon Extract Video Frames 🦝", "RaccoonSaveImageMetadata": "Raccoon Save Image + Metadata 🦝", "RaccoonSaveVideoMetadata": "Raccoon Save Video + Metadata 🦝", "RaccoonCheckpointLoader": "Raccoon Checkpoint Loader 🦝", "RaccoonDiffusionModelLoader": "Raccoon Diffusion Model Loader 🦝", "RaccoonLoraImporter": "Raccoon Lora Importer 🦝" }
WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
