#!/usr/bin/env python3
"""Idempotent, self-healing config.yaml manager for the CEO OS layer.

Replaces the previous fragile bash/awk merge in ceo-os-entrypoint.sh, which
corrupted config.yaml whenever a prior `/model --global` had rewritten it via
yaml.dump (2-space list indent) — the awk branch then mixed a 4-space list
item with the 2-space one, producing invalid YAML, which wiped model.default
on the next boot ("No models provided" incident, 2026-05-24).

This script ALWAYS writes valid YAML and is self-healing: if the existing
config is unparseable, it is rebuilt from scratch, restoring model.default
from the HERMES_MODEL env var. It guarantees, idempotently:
  - skills.external_dirs contains the CEO skills dir
  - model.default is set (preserved if present, else seeded from HERMES_MODEL)
  - hooks (pre/post_tool_call) point at guard.py / audit.py
  - tool_loop_guardrails.hard_stop_enabled = true

Runs as root from the entrypoint (config is chowned to hermes by the upstream
entrypoint afterwards). Must be invoked with a Python that has pyyaml
(the app venv: /opt/hermes/.venv/bin/python).
"""
import os
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("[ceo-os-init] pyyaml unavailable to this interpreter — "
                     "skipping config ensure (config left untouched)\n")
    sys.exit(0)

HOME = os.environ.get("HERMES_HOME", "/opt/data")
CFG_PATH = os.path.join(HOME, "config.yaml")
CEO_DIR = "/opt/hermes/skills/ceo"
# Use a DATED Anthropic snapshot — the bare alias `claude-sonnet-4-6` is
# rejected by the Anthropic API ("not a valid model ID", incident 2026-05-24).
MODEL_FALLBACK = "claude-sonnet-4-5-20250929"
MODEL_ENV = (os.environ.get("HERMES_MODEL") or "").strip() or MODEL_FALLBACK
# Provider for rebuild-from-scratch: hardcode anthropic (works with the dated
# model + ANTHROPIC_API_KEY). NOT read from HERMES_INFERENCE_PROVIDER, which
# defaulted to openrouter and broke the bare-alias model during the incident.
PROVIDER_FALLBACK = "anthropic"

HOOKS_BLOCK = {
    "pre_tool_call": [
        {
            "command": "python3 /opt/hermes/scripts/hooks/guard.py",
            "matcher": "^(?:write_file|patch|terminal|execute_code)$",
            "timeout": 10,
        }
    ],
    "post_tool_call": [
        {"command": "python3 /opt/hermes/scripts/hooks/audit.py", "timeout": 10}
    ],
}

# Fallback provider chain (reliability — Risk #3). Tried in order when the primary
# (Anthropic direct) fails (rate-limit/auth/overload/outage). Both via OpenRouter
# (OPENROUTER_API_KEY already set): Sonnet 4.5 first (same model+quality, covers
# key rate-limit/auth), then Gemini 2.5 Pro to survive a total Anthropic outage.
# Slugs verified against openrouter.ai/api/v1/models 2026-06-20.
FALLBACK_BLOCK = [
    {"provider": "openrouter", "model": "anthropic/claude-sonnet-4.5"},
    {"provider": "openrouter", "model": "google/gemini-2.5-pro"},
]

# Voice replies (TTS) — Edge (free, no key, edge-tts + ffmpeg already in image).
# Makes the text_to_speech tool emit Russian voice bubbles when the model invokes
# it (e.g. user says "ответь голосом"). Read at tools/tts_tool.py:747 (tts.edge.voice).
TTS_BLOCK = {"provider": "edge", "edge": {"voice": "ru-RU-DmitryNeural"}}


def _load() -> dict:
    if not os.path.exists(CFG_PATH):
        return {}
    try:
        with open(CFG_PATH, encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
        if isinstance(loaded, dict):
            return loaded
        sys.stderr.write("[ceo-os-init] config.yaml is not a mapping — rebuilding\n")
    except Exception as exc:  # corrupted / invalid YAML
        sys.stderr.write(f"[ceo-os-init] config.yaml unparseable ({exc}) — rebuilding clean\n")
    return {}


def main() -> None:
    cfg = _load()

    # skills.external_dirs — ensure CEO dir present, preserve others, dedupe.
    skills = cfg.get("skills") if isinstance(cfg.get("skills"), dict) else {}
    ext = skills.get("external_dirs")
    ext = list(ext) if isinstance(ext, list) else []
    if CEO_DIR not in ext:
        ext.append(CEO_DIR)
    skills["external_dirs"] = ext
    # Disable himalaya — the CEO uses Gmail via the google-workspace OAuth path
    # (/mail, /calendar skills). himalaya (IMAP CLI) isn't installed and only
    # causes email-intent misroutes. Idempotent; preserves other disabled names.
    disabled = skills.get("disabled")
    disabled = list(disabled) if isinstance(disabled, list) else []
    if "himalaya" not in disabled:
        disabled.append("himalaya")
    skills["disabled"] = disabled
    cfg["skills"] = skills

    # model.default + provider — preserve non-empty existing values, else seed.
    # Both only kick in on rebuild-from-scratch; normal boots preserve whatever
    # `/model ... --global` persisted.
    model = cfg.get("model")
    if isinstance(model, dict):
        if not str(model.get("default") or "").strip():
            model["default"] = MODEL_ENV
        if not str(model.get("provider") or "").strip():
            model["provider"] = PROVIDER_FALLBACK
    elif isinstance(model, str) and model.strip():
        model = {"default": model.strip(), "provider": PROVIDER_FALLBACK}
    else:
        model = {"default": MODEL_ENV, "provider": PROVIDER_FALLBACK}
    cfg["model"] = model

    # Security hooks + loop guardrails (always set — idempotent).
    cfg["hooks"] = HOOKS_BLOCK
    tlg = cfg.get("tool_loop_guardrails") if isinstance(cfg.get("tool_loop_guardrails"), dict) else {}
    tlg["hard_stop_enabled"] = True
    cfg["tool_loop_guardrails"] = tlg

    # Fallback chain + TTS — seed once if absent or empty; preserve user changes
    # (a populated value is left untouched, mirroring model.default semantics).
    if not cfg.get("fallback_providers"):
        cfg["fallback_providers"] = FALLBACK_BLOCK
    tts = cfg.get("tts") if isinstance(cfg.get("tts"), dict) else None
    if not tts:
        cfg["tts"] = TTS_BLOCK
    else:
        # Repair the English default if a prior image left it (tts_tool default
        # is en-US-AriaNeural) — the CEO is Russian-speaking. Any other voice the
        # user picked is preserved.
        edge = tts.get("edge") if isinstance(tts.get("edge"), dict) else {}
        if str(edge.get("voice") or "").startswith("en-"):
            edge["voice"] = "ru-RU-DmitryNeural"
            tts["edge"] = edge
            cfg["tts"] = tts

    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    os.replace(tmp, CFG_PATH)
    sys.stderr.write(
        f"[ceo-os-init] config.yaml ensured (model.default={cfg['model'].get('default')}, "
        f"external_dirs={cfg['skills']['external_dirs']}, hooks+guardrails set, "
        f"fallback={len(cfg.get('fallback_providers') or [])} providers, "
        f"tts={cfg.get('tts', {}).get('provider', 'off')})\n"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never crash the boot over config-ensure; upstream entrypoint continues.
        sys.stderr.write(f"[ceo-os-init] ensure_config failed (non-fatal): {exc}\n")
        sys.exit(0)
