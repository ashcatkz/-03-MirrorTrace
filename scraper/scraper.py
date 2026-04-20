"""
MirrorTrace — Scraper avec APIs GRATUITES françaises (aucune clé requise)
- recherche-entreprises.api.gouv.fr (officiel, gratuit, sans inscription)
- annuaire-entreprises.data.gouv.fr (data.gouv.fr, open data)
- GPT-4o-mini OpenAI (seul service payant, ~0.01€/analyse)
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import schedule
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env.local")

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
log = logging.getLogger("mirrortrace")

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
DASHBOARD_WEBHOOK = os.getenv("DASHBOARD_WEBHOOK_URL", "http://localhost:3000/api/prospects/ingest")
SCRAPER_SECRET    = os.getenv("SCRAPER_SECRET", "mirrortrace-local-secret-2025")

STATE_FILE = Path(__file__).parent / "scraper_state.json"

# Client OpenAI optionnel
openai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        log.warning("openai non installé — pip install openai")


# --------------------------------------------------------------------------- #
# État persistant                                                              #
# --------------------------------------------------------------------------- #

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"seen_sirets": [], "last_run": None, "total_scraped": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- #
# SOURCE — API Recherche Entreprises (data.gouv.fr) — 100% GRATUIT            #
# Aucune clé API, aucune inscription requise                                   #
# Doc : https://recherche-entreprises.api.gouv.fr                             #
# --------------------------------------------------------------------------- #

NAF_LABELS = {
    "6201Z": "Programmation informatique",
    "6202A": "Conseil en systèmes informatiques",
    "7022Z": "Conseil pour les affaires et management",
    "7490B": "Activités spécialisées diverses",
    "8211Z": "Services administratifs combinés",
    "6920Z": "Activités comptables",
    "7311Z": "Activités des agences de publicité",
    "4791A": "Vente à distance sur catalogue",
    "5610A": "Restauration traditionnelle",
    "4120A": "Construction de maisons individuelles",
    "7010Z": "Activités des sièges sociaux",
    "6420Z": "Activités des sociétés holding",
    "7112B": "Ingénierie et études techniques",
    "8299Z": "Autres activités de soutien aux entreprises",
    "4752B": "Commerce articles bricolage",
}


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=16))
def fetch_nouvelles_entreprises(page: int = 1, par_page: int = 25) -> list[dict]:
    """
    API officielle française — aucune clé requise.
    Retourne les entreprises récemment créées.
    """
    params = {
        "page": page,
        "per_page": par_page,
        # Filtre : entreprises actives créées récemment
        "date_immatriculation_min": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
        "etat_administratif": "A",  # Actif uniquement
    }

    resp = httpx.get(
        "https://recherche-entreprises.api.gouv.fr/search",
        params=params,
        timeout=30,
        headers={"User-Agent": "MirrorTrace/1.0 (prospection-research)"},
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    log.info(f"[API Gouv] Page {page} — {len(results)} entreprises")
    return results


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=16))
def fetch_by_date_creation(date_str: str, page: int = 1) -> list[dict]:
    """
    Recherche par date de création exacte via l'API annuaire entreprises.
    """
    params = {
        "page": page,
        "per_page": 25,
        "date_immatriculation_min": date_str,
    }
    resp = httpx.get(
        "https://recherche-entreprises.api.gouv.fr/search",
        params=params,
        timeout=30,
        headers={"User-Agent": "MirrorTrace/1.0"},
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def fetch_all_new(date_depuis: str) -> list[dict]:
    """Récupère toutes les pages de nouvelles entreprises."""
    all_results = []
    page = 1
    while page <= 10:  # max 10 pages pour éviter de surcharger l'API
        try:
            batch = fetch_by_date_creation(date_depuis, page)
            if not batch:
                break
            all_results.extend(batch)
            if len(batch) < 25:
                break
            page += 1
            time.sleep(0.5)  # respecter les rate limits
        except Exception as e:
            log.warning(f"Erreur page {page}: {e}")
            break
    log.info(f"[API Gouv] Total récupéré : {len(all_results)} entreprises")
    return all_results


def normalize_gouv(result: dict) -> dict:
    """Normalise un résultat de l'API data.gouv.fr au format MirrorTrace."""
    # Récupérer le premier établissement (siège)
    matching = result.get("matching_etablissements", [{}])
    etab = matching[0] if matching else {}

    # Dirigeant
    dirigeants = result.get("dirigeants", [])
    if dirigeants:
        d = dirigeants[0]
        director = f"{d.get('prenoms', '')} {d.get('nom', '')}".strip()
    else:
        director = "Dirigeant inconnu"

    naf = etab.get("activite_principale", result.get("activite_principale", ""))
    naf_clean = naf.replace(".", "")

    return {
        "siret":             etab.get("siret", result.get("siren", "") + "00001"),
        "siren":             result.get("siren", ""),
        "nom_entreprise":    result.get("nom_complet", result.get("nom_raison_sociale", "Entreprise inconnue")),
        "dirigeants":        [{"nom_complet": director}],
        "code_naf":          naf_clean,
        "libelle_code_naf":  NAF_LABELS.get(naf_clean, etab.get("libelle_activite_principale", "")),
        "date_immatriculation": result.get("date_creation", datetime.now().strftime("%Y-%m-%d")),
        "adresse_ligne_1":   etab.get("adresse", ""),
        "ville":             etab.get("commune", ""),
        "code_postal":       etab.get("code_postal", ""),
        "forme_juridique":   result.get("nature_juridique", ""),
        "email":             None,
        "telephone":         None,
        "_source":           "api.gouv.fr",
    }


# --------------------------------------------------------------------------- #
# GPT-4o-mini — Analyse IA (optionnel — ~0.01€ par analyse)                   #
# --------------------------------------------------------------------------- #

FALLBACK_INSIGHTS = {
    "62": ("Startup tech récente — besoin urgent en comptabilité SaaS et gestion des stocks options.", "Comptabilité analytique + TVA intracommunautaire + liasse fiscale", 2200),
    "70": ("Société de conseil — facturation honoraires et suivi des missions clients.", "Tenue mensuelle + déclarations TVA + bilan + optimisation IS", 1800),
    "69": ("Activité libérale réglementée — déclarations BNC et suivi trésorerie.", "Comptabilité BNC + déclarations URSSAF + liasse 2035", 1200),
    "73": ("Agence créative — gestion des notes de frais et facturation clients.", "Comptabilité projets + facturation + gestion freelances", 1500),
    "56": ("Restaurant — gestion des caisses, TVA restauration et paie.", "Comptabilité commerce + TVA 10% + bulletins de paie", 1400),
    "41": ("BTP — suivi des chantiers, facturation situations et retenues de garantie.", "Comptabilité BTP + situations travaux + TVA", 2000),
}

def get_fallback_insight(naf: str) -> dict:
    prefix = naf[:2]
    if prefix in FALLBACK_INSIGHTS:
        insight, need, rev = FALLBACK_INSIGHTS[prefix]
    else:
        insight = "Nouvelle société — besoin en structuration comptable et déclarations fiscales."
        need = "Tenue comptable mensuelle + déclarations TVA + bilan annuel"
        rev = 1500
    return {"aiInsight": insight, "accountingNeed": need, "estimatedRevenue": rev}


def generate_ai_insight(company: dict) -> dict:
    if not openai_client:
        return get_fallback_insight(company.get("code_naf", ""))

    prompt = f"""Expert-comptable senior. Analyse cette nouvelle entreprise immatriculée.

Entreprise : {company.get('nom_entreprise', '')}
Forme juridique : {company.get('forme_juridique', '')}
Code NAF : {company.get('code_naf', '')} — {company.get('libelle_code_naf', '')}
Ville : {company.get('ville', 'France')}

JSON uniquement :
- aiInsight : accroche besoins probables (max 120 car.)
- accountingNeed : mission recommandée (max 150 car.)
- estimatedRevenue : tarif mensuel EUR (entier 800-5000)"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.7,
        )
        return json.loads(response.choices[0].message.content or "{}")
    except Exception as e:
        log.warning(f"GPT-4 erreur: {e} — fallback activé")
        return get_fallback_insight(company.get("code_naf", ""))


# --------------------------------------------------------------------------- #
# Transformation → format dashboard                                            #
# --------------------------------------------------------------------------- #

def transform(raw: dict, ai: dict) -> dict:
    directors = raw.get("dirigeants", [])
    director = directors[0].get("nom_complet", "Dirigeant inconnu") if directors else "Dirigeant inconnu"
    return {
        "id":               raw.get("siret", str(time.time())),
        "siret":            raw.get("siret", ""),
        "siren":            raw.get("siren", ""),
        "companyName":      raw.get("nom_entreprise", ""),
        "directorName":     director,
        "nafCode":          raw.get("code_naf", ""),
        "nafLabel":         raw.get("libelle_code_naf", ""),
        "createdAt":        raw.get("date_immatriculation", datetime.now().isoformat()),
        "address":          raw.get("adresse_ligne_1", ""),
        "city":             raw.get("ville", ""),
        "postalCode":       raw.get("code_postal", ""),
        "email":            raw.get("email"),
        "phone":            raw.get("telephone"),
        "status":           "identified",
        "aiInsight":        ai.get("aiInsight", ""),
        "accountingNeed":   ai.get("accountingNeed", ""),
        "estimatedRevenue": ai.get("estimatedRevenue", 1500),
        "scrapedAt":        datetime.now().isoformat(),
        "source":           raw.get("_source", "api.gouv.fr"),
    }


# --------------------------------------------------------------------------- #
# Push vers dashboard                                                          #
# --------------------------------------------------------------------------- #

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def push_to_dashboard(prospects: list[dict]) -> None:
    if not prospects:
        return
    resp = httpx.post(
        DASHBOARD_WEBHOOK,
        json={"prospects": prospects},
        headers={"Content-Type": "application/json", "X-Scraper-Secret": SCRAPER_SECRET},
        timeout=15,
    )
    resp.raise_for_status()
    log.info(f"[Dashboard] ✓ {len(prospects)} prospects envoyés")


def save_offline(prospects: list[dict]) -> None:
    queue = Path(__file__).parent / "offline_queue.jsonl"
    with queue.open("a", encoding="utf-8") as f:
        for p in prospects:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    log.warning(f"{len(prospects)} prospects sauvegardés hors-ligne (dashboard injoignable)")


# --------------------------------------------------------------------------- #
# Cycle principal                                                              #
# --------------------------------------------------------------------------- #

def run_cycle() -> None:
    console.rule("[gold1]MirrorTrace — Cycle scraping[/gold1]")
    state = load_state()
    seen  = set(state.get("seen_sirets", []))

    last_run = state.get("last_run")
    date_depuis = (
        datetime.fromisoformat(last_run).strftime("%Y-%m-%d")
        if last_run
        else (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d")
    )
    log.info(f"Recherche depuis : {date_depuis}")

    # Collecte depuis l'API officielle gratuite
    raw_list = []
    try:
        raw_list = fetch_all_new(date_depuis)
    except Exception as e:
        log.error(f"Erreur API: {e}")
        return

    new_prospects = []
    for result in raw_list:
        company = normalize_gouv(result)
        siret = company.get("siret", "")

        if not siret or siret in seen:
            continue

        log.info(f"  → {siret} | {company.get('nom_entreprise', '')[:50]}")

        ai_data = generate_ai_insight(company)
        new_prospects.append(transform(company, ai_data))
        seen.add(siret)
        time.sleep(0.2)

    if new_prospects:
        try:
            push_to_dashboard(new_prospects)
        except Exception as e:
            log.error(f"Envoi échoué: {e}")
            save_offline(new_prospects)

    state["seen_sirets"]   = list(seen)[-10000:]
    state["last_run"]      = datetime.now().isoformat()
    state["total_scraped"] = state.get("total_scraped", 0) + len(new_prospects)
    save_state(state)

    console.print(
        f"[bold green]✓[/bold green] "
        f"[gold1]{len(new_prospects)} nouveaux[/gold1] / "
        f"{state['total_scraped']} total"
    )


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    console.print("\n[bold gold1]  MirrorTrace Scraper  [/bold gold1]\n", justify="center")

    status_gpt = "[green]GPT-4o-mini ✓[/green]" if openai_client else "[yellow]GPT-4 absent → analyse basique activée[/yellow]"
    console.print(f"Source données : [green]api.gouv.fr ✓ (gratuit, sans clé)[/green]")
    console.print(f"Analyse IA     : {status_gpt}")
    console.print()

    run_cycle()

    schedule.every(30).minutes.do(run_cycle)
    log.info("Planificateur actif — cycle toutes les 30 min. Ctrl+C pour arrêter.")
    while True:
        schedule.run_pending()
        time.sleep(60)
