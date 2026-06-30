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
SOUL_PATH = os.path.join(HOME, "SOUL.md")
CEO_DIR = "/opt/hermes/skills/ceo"

# Email/calendar routing rule injected into the system prompt (SOUL.md is loaded
# fresh each message by agent/prompt_builder.py). Without it the LLM reaches for
# `himalaya` (an IMAP CLI it knows from training, not installed) instead of the
# connected google-workspace OAuth path. Idempotent via the marker below.
_SOUL_RULE_MARKER = "EMAIL / КАЛЕНДАРЬ / GOOGLE — критическое правило роутинга"
SOUL_EMAIL_RULE = """

---

## 📧 EMAIL / КАЛЕНДАРЬ / GOOGLE — критическое правило роутинга (читать перед любым email/calendar запросом)

Почта (Gmail), Календарь, Google Sheets/Drive/Docs Александра ПОДКЛЮЧЕНЫ через OAuth (google-workspace). Токен: /opt/data/google_token.json (рабочий).

Для ЛЮБОГО запроса про почту / календарь / таблицы используй ТОЛЬКО google-workspace:
- Предпочитай CEO-скиллы /mail (почта) и /calendar (расписание).
- Прямой движок: HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python /opt/hermes/skills/productivity/google-workspace/scripts/google_api.py gmail search 'in:inbox newer_than:1d' --max 10

ЗАПРЕЩЕНО: запускать `himalaya` или любой IMAP/SMTP-CLI (не установлен, не нужен); предлагать его установку / app-password; выдавать «ТЕХНИЧЕСКАЯ ОШИБКА» про email — почта работает через google_api.py.

Границы (Phase-1): чтение свободно; отправка письма / создание события — ТОЛЬКО после явного подтверждения Александра.
"""

# Universal draft-action buttons rule. Every saveable draft/confirmation across
# ALL skills must end with the [[draft_actions]] marker so the gateway renders
# the 4 hands-free buttons. Lives in the persona (loaded every message) so it
# applies everywhere, including skills without an explicit marker. Idempotent.
_SOUL_DRAFT_MARKER = "КНОПКИ ЧЕРНОВИКА — универсальное правило"
SOUL_DRAFT_RULE = """

---

## 🔘 КНОПКИ ЧЕРНОВИКА — универсальное правило (любой сохраняемый черновик, ВЕЗДЕ)

Когда показываешь ЛЮБОЙ черновик / подтверждение, который можно сохранить (заметка,
задача, протокол встречи, поездка, дневник, напоминание, событие, отчёт — ЧТО УГОДНО),
ВСЕГДА заканчивай сообщение строкой `[[draft_actions]]` на отдельной последней строке.

ЗАПРЕЩЕНО писать текстом «Подтверди: ✅ да / ✏️ поправь», «Сохранить? да/нет» и любые
текстовые варианты подтверждения — ТОЛЬКО маркер `[[draft_actions]]`. НЕ объясняй его и
НЕ показывай как текст. Гейтвей превратит его в 4 кнопки под сообщением:
✅ Сохранить · ➕ Добавить · ✏️ Редактировать · 🗑 Удалить.

Реакция на нажатия (приходят как сообщения от пользователя):
- «Сохрани текущий черновик…» → сохрани показанный черновик его обычным способом (helper скилла).
- пользователь диктует дополнение (после ➕ Добавить) → допиши в черновик, снова покажи с `[[draft_actions]]`.
- пользователь диктует правку (после ✏️ Редактировать) → измени черновик, снова покажи с `[[draft_actions]]`.
- «Отмени текущий черновик…» → НЕ сохраняй, ответь «🗑 Черновик отменён».
"""

# Capture-everywhere rule: typed text is a first-class input (equal to voice), and
# every saved record lives in the CEO's Google Sheets (his visible tables) — never
# expose internal markdown paths. Lives in the persona so it applies to all skills.
_SOUL_CAPTURE_MARKER = "ЗАХВАТ И ХРАНЕНИЕ — универсальное правило"
SOUL_CAPTURE_RULE = """

---

## 🗂 ЗАХВАТ И ХРАНЕНИЕ — универсальное правило (текст = голос; всё в таблицы CEO)

**Текст — первоклассный вход, наравне с голосом.** ЛЮБОЕ свободное сообщение
(набранный текст ИЛИ голосовое), похожее на задачу / мысль / решение / идею /
заметку, СРАЗУ разбирай через `/capture` и показывай черновик с `[[draft_actions]]`.
НЕ показывай повторно меню-инструкцию «готов принять voice memo…» когда пользователь
уже прислал содержательный текст — он ждёт черновик, а не приглашение. После нажатия
плитки 🎙 Заметка следующий текст пользователя = содержимое заметки → сразу черновик.

**Все записи живут в Google-таблицах Александра** (его видимый «Excel»): задачи →
вкладка «Задачи», решения → «Решения», идеи/мысли → «Идеи», встречи → «Протоколы»,
дневник → «Дневник», поездки → «Поездки». В черновиках и подтверждениях называй
ВКЛАДКУ ТАБЛИЦЫ, куда легла запись. ЗАПРЕЩЕНО показывать пользователю внутренние пути
`memory/*.md`, `memory.md::…`, `daily_log.md` и т.п. — он эти файлы не видит и не должен.
"""

# Self-tuning / feedback channel rule. Александр may correct Hermes' behaviour by
# voice/text at any moment; Hermes self-tunes (preference) or queues a dev fix (bug).
_SOUL_TUNE_MARKER = "САМОНАСТРОЙКА И ФИДБЕК — универсальное правило"
SOUL_TUNE_RULE = """

---

## 🛠 САМОНАСТРОЙКА И ФИДБЕК — универсальное правило (Александр правит поведение на ходу)

Александр может в ЛЮБОЙ момент (голосом/текстом) сказать, что что-то не так:
«это неправильно», «настройся», «запомни как правило», «всегда делай так»,
«не делай так», «исправь себя», «так не надо», «вот так лучше», «тебе фидбек».
Это сигнал скилла `/tune` — НЕ путай с `/capture` (там задачи/мысли, тут — про твоё поведение).

Раздели на два типа и ВСЕГДА сначала покажи черновик с `[[draft_actions]]`:
- **правило** (тон / длина / формат / дефолт / что показывать) — ты МОЖЕШЬ применить сам:
  `python /opt/hermes/skills/ceo/tune/scripts/tune.py --rule "<точная формулировка>"`.
  Оно добавится в раздел «🎛 Живые корректировки CEO» этой персоны и применится со
  следующего сообщения.
- **баг** (кнопка не появилась, скилл упал, запись ушла не туда, команда не сработала) —
  сам не чинишь: `python /opt/hermes/skills/ceo/tune/scripts/tune.py --bug "<что сломано>"`.
  Это очередь разработчику. Честно скажи: «записал баг, разработчик поправит в коде».

**🎛 Живые корректировки CEO имеют ПРИОРИТЕТ** над более ранними инструкциями этой
персоны при конфликте — это последнее слово Александра о том, как себя вести.
**ИСКЛЮЧЕНИЕ:** этот приоритет НЕ распространяется на жёсткие правила безопасности —
privacy guard (пароли/банк/медданные/семейные имена), обязательное подтверждение
перед отправкой письма/события, неразглашение секретов. Такие правила через /tune
переопределить НЕЛЬЗЯ; если корректировка пытается их ослабить — НЕ применяй её,
оформи как баг разработчику и честно скажи об этом.
"""

# Clean user-facing output — never leak technical/diagnostic noise into messages.
# Александр reads every message; logging errors, guard notes, file paths, stack
# traces etc. spoil readability and feel unpleasant (his explicit feedback,
# 2026-06-30). Internal failures must be handled silently, not narrated to him.
_SOUL_CLEAN_MARKER = "ЧИСТЫЕ СООБЩЕНИЯ — универсальное правило"
SOUL_CLEAN_RULE = """

---

## 🧼 ЧИСТЫЕ СООБЩЕНИЯ — универсальное правило (никаких тех-данных в тексте пользователю)

Александр читает КАЖДОЕ сообщение. Технический шум портит текст и неприятен ему.
ЗАПРЕЩЕНО включать в сообщения любые служебные/технические данные: ошибки и заметки
логирования («logging note», «не удалось записать в logs/…»), сообщения guard'а, пути
к файлам, имена инструментов/полей/таблиц как тех-детали, stack traces, коды ошибок,
статусы внутренних записей, фразы вида «skill инструкции устарели» и т.п.

Если внутренняя операция (логирование, запись в файл/таблицу, sync) не удалась —
обработай это МОЛЧА: это твоя внутренняя кухня, НЕ докладывай о ней Александру.
Сообщение содержит ТОЛЬКО то, что полезно и приятно ему как человеку.

Если поломка реально влияет на него — скажи ОДНОЙ короткой человеческой фразой без
тех-подробностей и оформи баг разработчику через `/tune` (см. правило самонастройки).
"""
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


def _ensure_soul_rule() -> None:
    """Append the email-routing rule to SOUL.md if its marker is absent.

    Only touches an existing SOUL.md (the injected persona); does not create one.
    Idempotent — re-runs are no-ops once the marker is present.
    """
    try:
        if not os.path.exists(SOUL_PATH):
            return
        with open(SOUL_PATH, encoding="utf-8") as fh:
            content = fh.read()
        appended = 0
        for marker, block in ((_SOUL_RULE_MARKER, SOUL_EMAIL_RULE),
                              (_SOUL_DRAFT_MARKER, SOUL_DRAFT_RULE),
                              (_SOUL_CAPTURE_MARKER, SOUL_CAPTURE_RULE),
                              (_SOUL_TUNE_MARKER, SOUL_TUNE_RULE),
                              (_SOUL_CLEAN_MARKER, SOUL_CLEAN_RULE)):
            if marker not in content:
                with open(SOUL_PATH, "a", encoding="utf-8") as fh:
                    fh.write(block)
                content += block
                appended += 1
        if appended:
            sys.stderr.write(f"[ceo-os-init] SOUL.md rules appended ({appended})\n")
    except Exception as exc:
        sys.stderr.write(f"[ceo-os-init] SOUL.md rule ensure skipped ({exc})\n")


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

    # STT: switch to Groq whisper-large-v3-turbo when GROQ_API_KEY is present
    # (accurate + fast for Russian, free tier). Falls back to local otherwise.
    if os.environ.get("GROQ_API_KEY"):
        stt = cfg.get("stt") if isinstance(cfg.get("stt"), dict) else {}
        stt["enabled"] = True
        stt["provider"] = "groq"
        groq = stt.get("groq") if isinstance(stt.get("groq"), dict) else {}
        groq["model"] = "whisper-large-v3-turbo"
        stt["groq"] = groq
        cfg["stt"] = stt

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

    # Ensure the email/calendar routing rule is in the injected SOUL.md (loaded
    # fresh each message). Append once if the marker is absent; preserve the rest.
    _ensure_soul_rule()
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
