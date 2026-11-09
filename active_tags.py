# Raccoon Active Tags — shows (and outputs) the trigger / positive / negative tags of every LoRA that is ON
# in the graph's Power Lora Loader (rgthree) nodes, plus the active checkpoint / diffusion model.
#
# All the live work is client-side (js/raccoon_active_tags.js): it watches the graph, asks the RaccoonAI
# API (POST /api/model-tags/resolve) for the tags stored in the DB and writes the joined text into the two
# hidden widgets below. Python only hands those widget values out as STRING outputs at queue time, so the
# outputs keep working even when the API is offline (last resolved text) and in API-format prompts.


class RaccoonActiveTags:
    CATEGORY = "RaccoonAI"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("positive", "negative")
    FUNCTION = "get_tags"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive_text": ("STRING", {"multiline": False, "default": ""}),
                "negative_text": ("STRING", {"multiline": False, "default": ""}),
            }
        }

    def get_tags(self, positive_text, negative_text):
        return (positive_text or "", negative_text or "")


NODE_CLASS_MAPPINGS = {"RaccoonActiveTags": RaccoonActiveTags}
NODE_DISPLAY_NAME_MAPPINGS = {"RaccoonActiveTags": "Raccoon Active Tags 🦝"}
