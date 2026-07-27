"""LLM-based company classification via the Claude API — replaces keyword-matching for the
"co ta firma naprawdę robi" question (see e.g. Siemens Suisse being mislabeled "producent/obróbka
mechaniczna" because 'Feinmechanik' was one of 20 unrelated technologies in its boilerplate
purpose statement — a keyword match can't tell "1 word in a giant list" from "the company's real
focus", an LLM reading the full text can).

Two entry points:
- classify_company(): one company, synchronous — for quick tests/spot-checks.
- classify_companies_batch(): many companies (up to 100k) via the Message Batches API — 50%
  cheaper than synchronous calls, meant for "run this on all 200 companies at once".

Setup: copy .env.example to .env and set ANTHROPIC_API_KEY (console.anthropic.com). Never commit
.env — it's already gitignored.
"""
import os
import time
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5"  # good judgment-to-cost ratio for this task; claude-haiku-4-5 is cheaper if budget is the only concern

# Fixed vocabulary so tags stay consistent across companies instead of the model inventing
# near-duplicate phrasings ("obróbka CNC" vs "CNC machining") for the same concept.
PRODUCT_TAGS = [
    "rozdzielnice SN/WN", "transformatory", "wyłączniki/rozłączniki",
    "obróbka mechaniczna/CNC", "odlewy/odlewnictwo", "łożyska",
    "hydraulika/pneumatyka", "elektronika/automatyka", "kable/przewody",
    "uszczelnienia", "dystrybucja komponentów elektrycznych",
    "inżynieria/projektowanie", "maszyny przemysłowe (ogólne)",
    "wyposażenie morskie", "inne",
]
BUSINESS_MODELS = [
    "producent", "dystrybutor/handel", "usługodawca (inżynieria/serwis)",
    "konglomerat wieloprofilowy", "inne",
]
RELEVANCE_LEVELS = ["wysoka", "średnia", "niska", "brak"]


class CompanyClassification(BaseModel):
    one_line_summary: str = Field(description="Krótkie podsumowanie po polsku, czym firma faktycznie się zajmuje")
    product_tags: list[str] = Field(description="1-3 tagi z ustalonej listy, najbardziej trafne")
    business_model: str
    relevance_to_switchgear: str = Field(
        description="Czy firma plausibly dostarcza komponenty SN/WN (rozdzielnice, transformatory, "
                     "wyłączniki) lub pokrewne branże (obróbka mechaniczna, maszyny przemysłowe)"
    )
    relevance_reason: str = Field(description="1 zdanie uzasadnienia oceny relevance_to_switchgear")


CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "one_line_summary": {"type": "string"},
        "product_tags": {"type": "array", "items": {"type": "string", "enum": PRODUCT_TAGS}},
        "business_model": {"type": "string", "enum": BUSINESS_MODELS},
        "relevance_to_switchgear": {"type": "string", "enum": RELEVANCE_LEVELS},
        "relevance_reason": {"type": "string"},
    },
    "required": ["one_line_summary", "product_tags", "business_model", "relevance_to_switchgear", "relevance_reason"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Jesteś analitykiem klasyfikującym szwajcarskie firmy dla jednoosobowego VAD \
(Value-Added Distributor) w segmencie części zamiennych do rozdzielnic średniego i wysokiego \
napięcia (GIS/MV-HV). Dostajesz nazwę firmy i pełny tekst celu działalności (Zweck der \
Gesellschaft) z rejestru handlowego Zefix.

Oceń, czym firma FAKTYCZNIE się zajmuje jako główną działalnością — nie tylko jakie pojedyncze \
słowa pojawiają się w opisie. W szczególności: duży konglomerat wymieniający dziesiątki \
niepowiązanych technologii w ramach ogólnikowego celu statutowego (typowe dla dużych spółek \
akcyjnych) powinien dostać relevance_to_switchgear = "niska" lub "brak", nawet jeśli jedno z \
wymienionych słów technicznie pasuje do naszej branży — chyba że ta konkretna technologia jest \
wyraźnie centralnym, a nie pobocznym elementem opisu."""


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — copy .env.example to .env and fill it in")
    return anthropic.Anthropic(api_key=api_key)


def _build_prompt(name: str, description: str) -> str:
    return f"Firma: {name}\n\nCel działalności (z rejestru): {description}"


def classify_company(name: str, description: str, model: str = DEFAULT_MODEL) -> CompanyClassification:
    """Single synchronous call — for quick tests, not for bulk runs (use classify_companies_batch)."""
    client = _client()
    response = client.messages.create(
        model=model,
        # claude-sonnet-5 runs adaptive thinking by default when `thinking` is omitted, and
        # max_tokens caps thinking + response text together — 500 was too tight and truncated
        # the JSON mid-string. 2048 leaves headroom for both at effort=medium.
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_prompt(name, description)}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": CLASSIFICATION_SCHEMA}},
    )
    text = next(b.text for b in response.content if b.type == "text")
    return CompanyClassification.model_validate_json(text)


def classify_companies_batch(
    companies: list[tuple[str, str, str]],
    model: str = DEFAULT_MODEL,
    poll_interval: int = 10,
) -> dict[str, Optional[CompanyClassification]]:
    """Classify many companies in one Message Batches run (50% cheaper than sync calls, up to
    100k requests/batch, usually completes within an hour). `companies` is a list of
    (custom_id, name, description) — custom_id should be something you can map back to your
    record (e.g. dedup_key). Returns {custom_id: CompanyClassification or None on failure}."""
    client = _client()
    requests = [
        Request(
            custom_id=custom_id,
            params=MessageCreateParamsNonStreaming(
                model=model,
                max_tokens=2048,  # see classify_company() — adaptive thinking shares this budget
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_prompt(name, description)}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": CLASSIFICATION_SCHEMA}},
            ),
        )
        for custom_id, name, description in companies
    ]

    batch = client.messages.batches.create(requests=requests)
    print(f"[llm_classify] batch {batch.id} created with {len(requests)} request(s)")

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print(f"[llm_classify] batch {batch.id}: {batch.processing_status} "
              f"(processing={batch.request_counts.processing}, succeeded={batch.request_counts.succeeded})")
        time.sleep(poll_interval)

    results: dict[str, Optional[CompanyClassification]] = {}
    for result in client.messages.batches.results(batch.id):
        if result.result.type == "succeeded":
            text = next(b.text for b in result.result.message.content if b.type == "text")
            try:
                results[result.custom_id] = CompanyClassification.model_validate_json(text)
            except Exception as e:
                print(f"[llm_classify] failed to parse result for {result.custom_id}: {e}")
                results[result.custom_id] = None
        else:
            print(f"[llm_classify] batch item {result.custom_id} failed: {result.result.type}")
            results[result.custom_id] = None
    return results


if __name__ == "__main__":
    # Spot-check on the known tricky cases from this conversation before running a full batch.
    test_cases = [
        ("Siemens Suisse SA", """Der Zweck der Gesellschaft ist die Entwicklung, die Herstellung, der Erwerb und der Vertrieb von Erzeugnissen auf dem Gebiet der Elektrotechnik und der Elektronik, insbesondere der Telekommunikations- und Datentechnik, der Schwach- und Starkstromtechnik, der medizinischen Technik, der Gebäudetechnik und der Gebäudebewirtschaftung sowie des Maschinenbaus, der Feinmechanik und verwandter Techniken; die Planung, die Ausführung und der Vertrieb von Anlagen und Teilen von Anlagen zur Erzeugung, Übermittlung und Verarbeitung von Informationen und Energie sowie deren Anwendung auf Erzeugnisse aller Art."""),
        ("Precisteel Sàrl", """Die Gesellschaft bezweckt den Betrieb eines Unternehmens in der Mechanik-Branche, mit Filialen im europäischen Raum, in den Bereichen Décolletage, Metall im Allgemeinen, Schweisserei, Galvage, Metall- und Maschinenbau, Bearbeitung aller Arten von Plastik, Montage und Reparaturen, Elektronik sowie Import/Export und Kauf/Verkauf von Waren aller Art sowie Marketing dieser Artikel."""),
        ("hr-Feinmechanik SA", """Konstruktion, Entwicklung, Herstellung und Verkauf von sowie Handel mit Waren und Gütern, insbesondere mit Bestandteilen für Industriemaschinen sowie Sammlern und Verteilern für Erdwärmesonden als auch Erbringen von Service-, Wartungs- und Beratungsdienstleistungen in diesen Bereichen."""),
        ("Leitner SA", """Entwicklung, die Herstellung und den Verkauf chirurgischer Instrumente für die Medizinaltechnik, von Maschinenbauteilen und anderer Geräten und Teilen der Feinmechanik sowie den Handel mit diesen Produkten."""),
    ]
    for name, description in test_cases:
        result = classify_company(name, description)
        print(f"\n=== {name} ===")
        print(result.model_dump_json(indent=2))
