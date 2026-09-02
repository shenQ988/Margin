"""Shared LLM provider/runtime construction for the hallucination-eval scripts.

Deliberately duplicated from eval/run_eval.py's equivalent logic rather
than imported from it or refactored out into a shared module — the task
that added this package was explicitly scoped to not modify any existing
eval/ file. This is the one piece that would otherwise need touching
run_eval.py, so it's copied here instead (~20 lines, low risk of drift).
"""

from __future__ import annotations

import sys

from nanobot.config.loader import ConfigLoadError, load_config, resolve_config_env_vars
from nanobot.providers.base import LLMProvider
from nanobot.providers.factory import make_provider
from nanobot.utils.llm_runtime import LLMRuntime


def build_provider_and_runtime(preset_name: str | None = None) -> tuple[LLMProvider, LLMRuntime]:
    """Build a real, configured LLMProvider + LLMRuntime from the user's
    nanobot config. Exits the process with a clear message on failure —
    this is CLI-script plumbing, not a library function."""
    try:
        config = resolve_config_env_vars(load_config())
    except ConfigLoadError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        preset = config.resolve_preset(preset_name)
        provider = make_provider(config, preset_name=preset_name)
    except (ValueError, KeyError) as exc:
        print(
            f"Could not build an LLM provider from your nanobot config: {exc}\n"
            "Configure at least one provider (see `nanobot onboard` or "
            "~/.nanobot/config.json) before running this.",
            file=sys.stderr,
        )
        sys.exit(1)

    runtime = LLMRuntime.capture(
        provider,
        preset.model,
        context_window_tokens=preset.context_window_tokens,
        model_preset=preset_name,
    )
    return provider, runtime
