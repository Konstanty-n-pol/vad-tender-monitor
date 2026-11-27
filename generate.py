"""Render the email digest and dashboard HTML from stored records. Same data, two views."""
from datetime import date, datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

import storage
from filters import classify_activity_category_display
import i18n

TEMPLATES_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR = Path(__file__).parent / "docs"  # GitHub Pages serves from /docs on main branch

env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
# All user-facing text is English; see i18n.py for the render-time translation of stored values.
env.globals["country_name"] = i18n.country_name


def _localize_records(records: list) -> None:
    """Dict rows from storage: English category/reason, display title (title_en if translated)."""
    for r in records:
        r["activity_category"] = i18n.category_en(r.get("activity_category"))
        r["reason"] = i18n.reason_en(r.get("reason"))
        r["display_title"] = r.get("title_en") or r["title"]


def _localize_new(records: list) -> list:
    """Record objects for the email: same treatment, without mutating the originals' stored text."""
    out = []
    for r in records:
        out.append({
            "title": r.title, "display_title": getattr(r, "title_en", None) or r.title,
            "url": r.url, "source": r.source, "country": r.country, "category": r.category,
            "buyer": r.buyer, "deadline": r.deadline, "value_estimate": r.value_estimate,
            "commodity_tier": r.commodity_tier, "website": r.website,
            "reason": i18n.reason_en(r.reason), "activity_category": i18n.category_en(r.activity_category),
        })
    return out


def _days_since(iso_date: str) -> int:
    try:
        return (date.today() - datetime.fromisoformat(iso_date).date()).days
    except ValueError:
        return 0


def render_email(new_records: list, dashboard_url: str) -> str:
    tpl = env.get_template("email.html.j2")
    rows = _localize_new(new_records)
    tenders = [r for r in rows if r["category"] == "tender"]
    companies = [r for r in rows if r["category"] == "company"]
    news = [r for r in rows if r["category"] == "news"]
    return tpl.render(
        run_date=date.today().isoformat(),
        tenders=tenders, companies=companies, news=news,
        dashboard_url=dashboard_url,
    )


def _apply_relationships(records: list) -> None:
    """Append any known business relationships (storage.relationships table) onto `reason`,
    at render time only — never persisted back into the record itself."""
    by_company = {}
    for rel in storage.all_relationships():
        by_company.setdefault(rel["company_title"], []).append(rel)
    for r in records:
        rels = by_company.get(r["title"])
        if not rels:
            continue
        notes = "; ".join(
            f"{rel['relation_type']}: {rel['related_company']}" + (f" ({rel['note']})" if rel["note"] else "")
            for rel in rels
        )
        r["reason"] = f"{r['reason']} | {notes}" if r["reason"] else notes


def render_dashboard() -> str:
    tpl = env.get_template("dashboard.html.j2")
    records = storage.all_records()
    for r in records:
        r["days_since"] = _days_since(r["date_first_seen"])
        r["activity_category"] = classify_activity_category_display(
            r["keywords_matched"], r["llm_product_tags"], r["activity_category"]
        )
    _apply_relationships(records)
    _localize_records(records)
    sources = sorted({r["source"] for r in records})
    categories = sorted({r["activity_category"] for r in records if r["activity_category"]})
    countries = sorted({r["country"] for r in records if r["country"]}, key=i18n.country_name)
    return tpl.render(run_date=date.today().isoformat(), records=records, sources=sources,
                      categories=categories, countries=countries)


def write_dashboard():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = render_dashboard()
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate] wrote {OUTPUT_DIR / 'index.html'}")


def render_distributors_email(new_records: list, dashboard_url: str) -> str:
    tpl = env.get_template("distributors_email.html.j2")
    return tpl.render(
        run_date=date.today().isoformat(),
        new_records=_localize_new(new_records),
        dashboard_url=dashboard_url,
    )


def render_distributors_dashboard() -> str:
    tpl = env.get_template("distributors_dashboard.html.j2")
    records = storage.all_distributor_records()
    for r in records:
        r["activity_category"] = classify_activity_category_display(
            r["keywords_matched"], r["llm_product_tags"], r["activity_category"]
        )
    _apply_relationships(records)
    _localize_records(records)
    categories = sorted({r["activity_category"] for r in records if r["activity_category"]})
    return tpl.render(run_date=date.today().isoformat(), records=records, categories=categories)


def write_distributors_dashboard():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = render_distributors_dashboard()
    (OUTPUT_DIR / "distributors.html").write_text(html, encoding="utf-8")
    print(f"[generate] wrote {OUTPUT_DIR / 'distributors.html'}")
