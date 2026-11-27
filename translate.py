"""Translate tender titles to English with Claude (added 2026-11-27).

Runs after each weekly upsert (main.py): every tender in storage without `title_en` gets one.
Prozorro titles are Ukrainian, TED titles mix English CPV labels with the buyer's language
(Romanian, Greek, Czech...), SIMAP titles are German/French/Italian. Company titles are names and
are left alone. Needs ANTHROPIC_API_KEY (locally from .env, in CI from the repo secret); without
it the step is skipped and the dashboard/email simply show the original titles.

Cost: titles are short (~30 tokens); a weekly run of ~200 titles is a few cents on claude-opus-5-5.
"""
import json
import os

import anthropic

import storage

MODEL = "claude-opus-5-5"
BATCH_SIZE = 40

SYSTEM_PROMPT = """You translate public-procurement tender titles into concise, natural English for \
a procurement analyst. Titles may be in Ukrainian, Russian, Romanian, Greek, Czech, Portuguese, \
German, Polish or other EU languages, and TED titles are often "Country – CPV label – original title": \
in that case return just a clean English rendering of the whole title without repeating the country \
or duplicating the CPV label. Keep brand names, model names and product codes exactly as written \
(Starlink, Starlink Mini, V4, Gen3, Adaptis MiniKit, cable lengths, voltages). Keep tender/lot numbers. \
If a title is already English, return it unchanged. Do not add explanations."""

SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "en": {"type": "string"}},
                "required": ["id", "en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        try:  # local runs: same .env convention as llm_classify.py
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return anthropic.Anthropic()


def translate_titles(titles: list, client) -> list:
    """Translate a list of titles; returns English strings in the same order ('' if missing)."""
    payload = "\n".join(json.dumps({"id": i, "title": t}, ensure_ascii=False) for i, t in enumerate(titles))
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Translate each title (JSON lines):\n{payload}"}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"unexpected stop_reason: {response.stop_reason}")
    text = next(b.text for b in response.content if b.type == "text")
    by_id = {t["id"]: t["en"].strip() for t in json.loads(text)["translations"]}
    return [by_id.get(i, "") for i in range(len(titles))]


def translate_pending(limit: int = 500) -> int:
    """Fill title_en for untranslated tenders. Returns how many were translated."""
    pending = storage.untranslated_tenders(limit)
    if not pending:
        return 0
    client = _client()
    if client is None:
        print(f"[translate] skipped: ANTHROPIC_API_KEY not set ({len(pending)} title(s) pending)")
        return 0
    done = 0
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start:start + BATCH_SIZE]
        try:
            english = translate_titles([title for _, title in batch], client)
        except (anthropic.APIError, RuntimeError, ValueError, KeyError) as e:
            print(f"[translate] batch {start // BATCH_SIZE + 1} failed: {e}")
            continue  # left NULL, retried next run
        result = {key: en for (key, _), en in zip(batch, english) if en}
        storage.set_titles_en(result)
        done += len(result)
    print(f"[translate] translated {done}/{len(pending)} tender title(s)")
    return done


if __name__ == "__main__":
    translate_pending()
