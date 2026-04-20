"""
MirrorTrace — Scraper production avec Pappers + INSEE Sirene + GPT-4
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
from openai import OpenAI
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

PAPPERS_API_KEY   = os.getenv("PAPPERS_API_KEY", "")
SIRENE_API_TOKEN  = os.getenv("SIRENE_API_TOKEN", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
DASHBOARD_WEBHOOK = os.getenv("DASHBOARD_WEBHOOK_URL", "http://localhost:3000/api/prospects/ingest")
SCRAPER_SECRET    = os.getenv("SCRAPER_SECRET", "")

STATE_FILE = Path(__file__).parent / "scraper_state.json"

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# --------------------------------------------------------------------------- #
# État persistant                                                              #
# --------------------------------------------------------------------------- #

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"seen_sirets": [], "last_run": None, "total_scraped": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# SOURCE 1 — Pappers API                                                       #
# --------------------------------------------------------------------------- #

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=16))
def fetch_pappers(date_depuis: str, page: int = 1) -> list[dict]:
    """
    Récupère les entreprises immatriculées depuis `date_depuis`.
    Clé gratuite : https://www.pappers.fr/api  (50 req/jour)
    """
    if not PAPPERS_API_KEY:
        return []

    params = {
        "api_token": PAPPERS_API_KEY,
        "date_immatriculation_min": date_depuis,
        "precision": "standard",
        "par_page": 100,
        "page": page,
    }
    resp = httpx.get("https://api.pappers.fr/v2/recherche", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    companies = data.get("resultats", [])
    log.info(f"[Pappers] Page {page} — {len(companies)} sociétés")
    return companies


def fetch_all_pappers(date_depuis: str) -> list[dict]:
    all_companies = []
    page = 1
    while True:
        batch = fetch_pappers(date_depuis, page)
        if not batch:
            break
        all_companies.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        time.sleep(1)
    return all_companies


# --------------------------------------------------------------------------- #
# SOURCE 2 — INSEE Sirene API v3 (officielle, gratuite)                       #
# --------------------------------------------------------------------------- #

def get_sirene_token() -> str:
    """
    Le token Sirene peut être soit un Bearer JWT soit une clé directe.
    À renseigner dans SIRENE_API_TOKEN après inscription sur api.insee.fr
    """
    return SIRENE_API_TOKEN


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=16))
def fetch_sirene_new_sirets(date_depuis: str, debut: int = 0) -> list[dict]:
    """
    Recherche les établissements créés depuis `date_depuis` via INSEE Sirene.
    Inscription gratuite : https://api.insee.fr/catalogue/site/themes/wso2/subthemes/insee/pages/item-info.jag?name=Sirene&version=V3&provider=insee
    """
    token = get_sirene_token()
    if not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    # Filtre : établissements actifs créés récemment, hors micro-entrepreneurs seuls
    q = f"dateCreationEtablissement:[{date_depuis} TO *] AND etatAdministratifEtablissement:A"

    params = {
        "q": q,
        "nombre": 100,
        "debut": debut,
        "champs": ",".join([
            "siret", "siren", "denominationUniteLegale",
            "prenom1UniteLegale", "nomUniteLegale",
            "activitePrincipaleEtablissement",
            "dateCreationEtablissement",
            "geo_adresse", "codePostalEtablissement",
            "libelleCommuneEtablissement",
            "categorieJuridiqueUniteLegale",
            "trancheEffectifsUniteLegale",
        ]),
    }

    resp = httpx.get(
        "https://api.insee.fr/entreprises/sirene/V3/siret",
        headers=headers,
        params=params,
        timeout=30,
    )
    if resp.status_code == 401:
        log.error("[Sirene] Token invalide ou expiré — vérifie SIRENE_API_TOKEN")
        return []
    resp.raise_for_status()

    data = resp.json()
    etablissements = data.get("etablissements", [])
    log.info(f"[Sirene] Offset {debut} — {len(etablissements)} établissements")
    return etablissements


def fetch_all_sirene(date_depuis: str) -> list[dict]:
    all_etabs = []
    debut = 0
    while True:
        batch = fetch_sirene_new_sirets(date_depuis, debut)
        if not batch:
            break
        all_etabs.extend(batch)
        if len(batch) < 100:
            break
        debut += 100
        time.sleep(0.5)
    return all_etabs


def normalize_sirene(etab: dict) -> dict:
    """Convertit un établissement Sirene au format MirrorTrace."""
    ul = etab.get("uniteLegale", {})
    prenom = ul.get("prenom1UniteLegale", "")
    nom = ul.get("nomUniteLegale", "")
    denom = ul.get("denominationUniteLegale", "")
    director = f"{prenom} {nom}".strip() if (prenom or nom) else "Dirigeant inconnu"
    company = denom or director or "Entreprise inconnue"

    geo = etab.get("adresseEtablissement", {})
    naf = etab.get("activitePrincipaleEtablissement", "")

    return {
        "siret": etab.get("siret", ""),
        "siren": etab.get("siren", ""),
        "nom_entreprise": company,
        "dirigeants": [{"nom_complet": director}],
        "code_naf": naf.replace(".", ""),
        "libelle_code_naf": "",
        "date_immatriculation": etab.get("dateCreationEtablissement", ""),
        "adresse_ligne_1": geo.get("libelleVoieEtablissement", ""),
        "ville": geo.get("libelleCommuneEtablissement", ""),
        "code_postal": geo.get("codePostalEtablissement", ""),
        "forme_juridique": ul.get("categorieJuridiqueUniteLegale", ""),
        "_source": "sirene",
    }


# --------------------------------------------------------------------------- #
# GPT-4 — Curation IA                                                         #
# --------------------------------------------------------------------------- #

def generate_ai_insight(company: dict) -> dict:
    if not openai_client:
        log.warning("[GPT-4] OPENAI_API_KEY manquante — analyse désactivée")
        return {
            "aiInsight": "Analyse IA non disponible (clé OpenAI manquante).",
            "accountingNeed": "Tenue comptable standard + déclarations fiscales",
            "estimatedRevenue": 1500,
        }

    name      = company.get("nom_entreprise", "Entreprise")
    naf       = company.get("code_naf", "")
    naf_label = company.get("libelle_code_naf", "")
    city      = company.get("ville", "France")
    form      = company.get("forme_juridique", "")

    prompt = f"""Tu es expert-comptable senior spécialisé en prospection commerciale.
Analyse cette nouvelle entreprise immatriculée et génère une proposition personnalisée.

Entreprise : {name}
Forme juridique : {form}
Code NAF : {naf} — {naf_label}
Ville : {city}

Réponds UNIQUEMENT en JSON :
- aiInsight : accroche sur les besoins probables (max 120 caractères)
- accountingNeed : mission comptable recommandée (max 150 caractères)
- estimatedRevenue : tarif mensuel estimé en EUR (entier 800-5000)"""

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=200,
        temperature=0.7,
    )
    return json.loads(response.choices[0].message.content or "{}")


# --------------------------------------------------------------------------- #
# Transformation → format MirrorTrace                                          #
# --------------------------------------------------------------------------- #

def transform(raw: dict, ai: dict) -> dict:
    directors = raw.get("dirigeants", [])
    director = directors[0].get("nom_complet", "Dirigeant inconnu") if directors else "Dirigeant inconnu"
    return {
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
        "email":            raw.get("email", None),
        "phone":            raw.get("telephone", None),
        "status":           "identified",
        "aiInsight":        ai.get("aiInsight", ""),
        "accountingNeed":   ai.get("accountingNeed", ""),
        "estimatedRevenue": ai.get("estimatedRevenue", 1500),
        "scrapedAt":        datetime.now().isoformat(),
        "source":           raw.get("_source", "pappers"),
    }


# --------------------------------------------------------------------------- #
# Push dashboard                                                               #
# --------------------------------------------------------------------------- #

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def push_to_dashboard(prospects: list[dict]) -> None:
    if not prospects:
        return
    resp = httpx.post(
        DASHBOARD_WEBHOOK,
        json={"prospects": prospects},
        headers={
            "Content-Type": "application/json",
            "X-Scraper-Secret": SCRAPER_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    log.info(f"[Dashboard] {len(prospects)} prospects envoyés")


def save_offline(prospects: list[dict]) -> None:
    queue = Path(__file__).parent / "offline_queue.jsonl"
    with queue.open("a", encoding="utf-8") as f:
        for p in prospects:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    log.warning(f"{len(prospects)} prospects sauvegardés hors-ligne")


# --------------------------------------------------------------------------- #
# Cycle principal                                                              #
# --------------------------------------------------------------------------- #

def run_cycle() -> None:
    console.rule("[gold1]MirrorTrace — Cycle de scraping[/gold1]")
    state   = load_state()
    seen    = set(state.get("seen_sirets", []))

    # Fenêtre de recherche
    last_run = state.get("last_run")
    if last_run:
        date_depuis = datetime.fromisoformat(last_run).strftime("%Y-%m-%d")
    else:
        date_depuis = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d")

    log.info(f"Fenêtre : depuis {date_depuis}")

    # Collecte depuis toutes les sources disponibles
    raw_companies: list[dict] = []

    if PAPPERS_API_KEY:
        log.info("[Pappers] Activation...")
        try:
            raw_companies += fetch_all_pappers(date_depuis)
        except Exception as e:
            log.error(f"[Pappers] Échec: {e}")
    else:
        log.warning("[Pappers] Clé absente — ignoré")

    if SIRENE_API_TOKEN:
        log.info("[Sirene] Activation...")
        try:
            etabs = fetch_all_sirene(date_depuis)
            raw_companies += [normalize_sirene(e) for e in etabs]
        except Exception as e:
            log.error(f"[Sirene] Échec: {e}")
    else:
        log.warning("[Sirene] Token absent — ignoré")

    if not raw_companies:
        log.warning("Aucune source disponible — configure au moins une clé API")
        return

    # Dédupliquer + analyser
    new_prospects = []
    for company in raw_companies:
        siret = company.get("siret", "")
        if not siret or siret in seen:
            continue

        log.info(f"  → {siret} | {company.get('nom_entreprise', '')[:40]}")
        try:
            ai_data = generate_ai_insight(company)
            time.sleep(0.3)  # respect rate limit GPT
        except Exception as e:
            log.warning(f"GPT-4 échec pour {siret}: {e}")
            ai_data = {"aiInsight": "", "accountingNeed": "", "estimatedRevenue": 1500}

        new_prospects.append(transform(company, ai_data))
        seen.add(siret)

    # Envoi dashboard
    if new_prospects:
        try:
            push_to_dashboard(new_prospects)
        except Exception as e:
            log.error(f"Envoi dashboard échoué: {e}")
            save_offline(new_prospects)

    # Mise à jour état
    state["seen_sirets"]   = list(seen)[-10000:]
    state["last_run"]      = datetime.now().isoformat()
    state["total_scraped"] = state.get("total_scraped", 0) + len(new_prospects)
    save_state(state)

    console.print(
        f"[bold green]✓[/bold green] Cycle terminé — "
        f"[gold1]{len(new_prospects)} nouveaux[/gold1] / "
        f"{state['total_scraped']} total"
    )


# --------------------------------------------------------------------------- #
# Entrée                                                                       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    console.print(
        "\n[bold gold1]  MirrorTrace Scraper  [/bold gold1]\n",
        justify="center",
    )

    # Afficher les sources actives
    sources = []
    if PAPPERS_API_KEY:   sources.append("[green]Pappers ✓[/green]")
    else:                 sources.append("[red]Pappers ✗ (clé manquante)[/red]")
    if SIRENE_API_TOKEN:  sources.append("[green]Sirene ✓[/green]")
    else:                 sources.append("[red]Sirene ✗ (token manquant)[/red]")
    if OPENAI_API_KEY:    sources.append("[green]GPT-4 ✓[/green]")
    else:                 sources.append("[yellow]GPT-4 ✗ (analyse désactivée)[/yellow]")

    console.print("Sources : " + " | ".join(sources))
    console.print()

    # Premier cycle immédiat
    run_cycle()

    # Planifier toutes les 30 minutes
    schedule.every(30).minutes.do(run_cycle)
    log.info("Planificateur actif — prochain cycle dans 30 min. Ctrl+C pour arrêter.")

    while True:
        schedule.run_pending()
        time.sleep(60)
