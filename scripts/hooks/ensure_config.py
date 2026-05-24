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
MODEL_FALLBACK = "claude-sonnet-4-6"
MODEL_ENV = (os.environ.get("HERMES_MODEL") or "").strip() or MODEL_FALLBACK

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
    cfg["skills"] = skills

    # model.default — preserve a non-empty existing value, else seed from env.
    model = cfg.get("model")
    if isinstance(model, dict):
        if not str(model.get("default") or "").strip():
            model["default"] = MODEL_ENV
    elif isinstance(model, str) and model.strip():
        model = {"default": model.strip()}
    else:
        model = {"default": MODEL_ENV}
    cfg["model"] = model

    # Security hooks + loop guardrails (always set — idempotent).
    cfg["hooks"] = HOOKS_BLOCK
    tlg = cfg.get("tool_loop_guardrails") if isinstance(cfg.get("tool_loop_guardrails"), dict) else {}
    tlg["hard_stop_enabled"] = True
    cfg["tool_loop_guardrails"] = tlg

    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    os.replace(tmp, CFG_PATH)
    sys.stderr.write(
        f"[ceo-os-init] config.yaml ensured (model.default={cfg['model'].get('default')}, "
        f"external_dirs={cfg['skills']['external_dirs']}, hooks+guardrails set)\n"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never crash the boot over config-ensure; upstream entrypoint continues.
        sys.stderr.write(f"[ceo-os-init] ensure_config failed (non-fatal): {exc}\n")
        sys.exit(0)
