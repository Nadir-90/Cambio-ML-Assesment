import os
from typing import Literal

ToolVersion = Literal[
    "computer_use_20241022",
    "computer_use_20250124",
    "computer_use_20250429",
    "computer_use_20251124",
]

# Beta flag header value sent to the Anthropic API per tool version
BETA_FLAGS: dict[str, str | None] = {
    "computer_use_20241022": "computer-use-2024-10-22",
    "computer_use_20250124": "computer-use-2025-01-24",
    "computer_use_20250429": "computer-use-2025-01-24",
    "computer_use_20251124": "computer-use-2025-11-24",
}

# Display dimensions match what the session container is configured with
_WIDTH = int(os.environ.get("WIDTH", "1024"))
_HEIGHT = int(os.environ.get("HEIGHT", "768"))

# Hardcoded Anthropic tool parameter schemas.
# These are stable API specs — the only dynamic values are display dimensions,
# which are read from the same WIDTH/HEIGHT env vars used by the session container.
TOOL_SCHEMAS: dict[str, list[dict]] = {
    "computer_use_20241022": [
        {
            "type": "computer_20241022",
            "name": "computer",
            "display_width_px": _WIDTH,
            "display_height_px": _HEIGHT,
            "display_number": 1,
        },
        {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
        {"type": "bash_20250124", "name": "bash"},
    ],
    "computer_use_20250124": [
        {
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": _WIDTH,
            "display_height_px": _HEIGHT,
            "display_number": 1,
        },
        {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
        {"type": "bash_20250124", "name": "bash"},
    ],
    "computer_use_20250429": [
        {
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": _WIDTH,
            "display_height_px": _HEIGHT,
            "display_number": 1,
        },
        {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
        {"type": "bash_20250124", "name": "bash"},
    ],
    "computer_use_20251124": [
        {
            "type": "computer_20251124",
            "name": "computer",
            "display_width_px": _WIDTH,
            "display_height_px": _HEIGHT,
            "display_number": 1,
            "enable_zoom": True,
        },
        {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
        {"type": "bash_20250124", "name": "bash"},
    ],
}
