"""Render the email digest and dashboard HTML from stored records. Same data, two views."""
from datetime import date, datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

import storage
from filters import classify_activity_category_display

TEMPLATES_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR = Path(__file__).parent / "docs"  # GitHub Pages serves from /docs on main branch

env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))


def _days_since(iso_date: str) -> int:
    try:
        return (date.today() - datetime.fromisoformat(iso_date).date()).days
    except ValueError:
        return 0


def render_email(new_records: list, dashboard_url: str) -> str:
    tpl = env.get_template("email.html.j2")
    tenders = [r for r in new_records if r.category == "tender"]
    companies = [r for r in new_records if r.category == "company"]
    news = [r for r in new_records if r.category == "news"]
    return tpl.render(
        run_date=date.today().isoformat(),
        tenders=tenders, companies=companies, news=news,
        dashboard_url=dashboard_url,
    )


def render_dashboard() -> str:
    tpl = env.get_template("dashboard.html.j2")
    records = storage.all_records()
    for r in records:
        r["days_since"] = _days_since(r["date_first_seen"])
        r["activity_category"] = classify_activity_category_display(
            r["keywords_matched"], r["llm_product_tags"], r["activity_category"]
        )
    sources = sorted({r["source"] for r in records})
    categories = sorted({r["activity_category"] for r in records if r["activity_category"]})
    return tpl.render(run_date=date.today().isoformat(), records=records, sources=sources, categories=categories)


def write_dashboard():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = render_dashboard()
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate] wrote {OUTPUT_DIR / 'index.html'}")


def render_distributors_email(new_records: list, dashboard_url: str) -> str:
    tpl = env.get_template("distributors_email.html.j2")
    return tpl.render(
        run_date=date.today().isoformat(),
        new_records=new_records,
        dashboard_url=dashboard_url,
    )


def render_distributors_dashboard() -> str:
    tpl = env.get_template("distributors_dashboard.html.j2")
    records = storage.all_distributor_records()
    for r in records:
        r["activity_category"] = classify_activity_category_display(
            r["keywords_matched"], r["llm_product_tags"], r["activity_category"]
        )
    categories = sorted({r["activity_category"] for r in records if r["activity_category"]})
    return tpl.render(run_date=date.today().isoformat(), records=records, categories=categories)


def write_distributors_dashboard():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = render_distributors_dashboard()
    (OUTPUT_DIR / "distributors.html").write_text(html, encoding="utf-8")
    print(f"[generate] wrote {OUTPUT_DIR / 'distributors.html'}")
