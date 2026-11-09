class AnyType(str):
    def __ne__(self, other):
        return False

any_type = AnyType("*")


class RaccoonConfig:
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
                })
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "execute"
    CATEGORY = "RaccoonAI"
    OUTPUT_NODE = True

    def execute(self, extra, checkpoint=None, positive=None, negative=None, ksampler=None, ksampler_advanced=None):
        return {}


NODE_CLASS_MAPPINGS        = { "RaccoonConfig": RaccoonConfig }
NODE_DISPLAY_NAME_MAPPINGS = { "RaccoonConfig": "Raccoon Config 🦝" }
WEB_DIRECTORY = "./js"

# Raccoon Active Tags lives in its own module so it merges cleanly with the other node files.
from .active_tags import NODE_CLASS_MAPPINGS as _ACTIVE_TAGS_CLASSES, NODE_DISPLAY_NAME_MAPPINGS as _ACTIVE_TAGS_NAMES
NODE_CLASS_MAPPINGS.update(_ACTIVE_TAGS_CLASSES)
NODE_DISPLAY_NAME_MAPPINGS.update(_ACTIVE_TAGS_NAMES)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
