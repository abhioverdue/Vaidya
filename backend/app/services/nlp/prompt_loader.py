"""
Vaidya — prompt template loader
Loads versioned .txt prompt files from /app/prompts/
Caches in memory after first read.
Supports hot-reload in development via PROMPT_HOT_RELOAD=true env var.
"""

import os
from functools import lru_cache
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
HOT_RELOAD  = os.getenv("PROMPT_HOT_RELOAD", "false").lower() == "true"

# In-memory cache for production (avoid disk reads on every request)
_cache: dict[str, str] = {}


def load_prompt(filename: str) -> str:
    """
    Load a prompt template from the prompts directory.

    Args:
        filename: e.g. "symptom_extraction_v1.txt"

    Returns:
        File contents as string.

    Raises:
        FileNotFoundError if template doesn't exist.
    """
    if not HOT_RELOAD and filename in _cache:
        return _cache[filename]

    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {path}. "
            f"Expected in: {PROMPTS_DIR}"
        )

    content = path.read_text(encoding="utf-8").strip()
    _cache[filename] = content

    logger.debug("vaidya.prompts.loaded", file=filename, chars=len(content))
    return content


def get_extraction_system_prompt(version: str = "v1") -> str:
    """Return the symptom extraction system prompt."""
    return load_prompt(f"symptom_extraction_{version}.txt")


def get_few_shot_examples(version: str = "v1") -> list[dict]:
    """
    Parse few-shot examples file into a list of {input, output} dicts
    suitable for building Ollama chat messages.
    """
    raw = load_prompt(f"few_shot_examples_{version}.txt")
    examples = []

    # Parse blocks separated by blank lines starting with EXAMPLE_N:
    import re
    blocks = re.split(r"\nEXAMPLE_\d+:\n", raw)

    for block in blocks:
        block = block.strip()
        if not block or block.startswith("#"):
            continue
        if "INPUT:" in block and "OUTPUT:" in block:
            parts  = block.split("OUTPUT:", 1)
            inp    = parts[0].replace("INPUT:", "").strip()
            out    = parts[1].strip()
            examples.append({"input": inp, "output": out})

    return examples


def list_available_prompts() -> list[str]:
    """List all available prompt template files."""
    if not PROMPTS_DIR.exists():
        return []
    return [f.name for f in PROMPTS_DIR.glob("*.txt")]
