"""
MirrorTrace — Scraper automatique d'immatriculations
Surveille le flux Pappers / INSEE Sirene pour détecter chaque nouveau SIRET.
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

load_dotenv()

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
log = logging.getLogger("mirrortrace")

PAPPERS_API_KEY = os.getenv("PAPPERS_API_KEY", "")
SIRENE_API_TOKEN = os.getenv("SIRENE_API_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DASHBOARD_WEBHOOK = os.getenv("DASHBOARD_WEBHOOK_URL", "http://localhost:3000/api/prospects/ingest")

STATE_FILE = Path("scraper_state.json")

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# --------------------------------------------------------------------------- #
# État persistant — évite les doublons entre sessions                         #
# --------------------------------------------------------------------------- #

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seen_sirets": [], "last_run": None, "total_scraped": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Pappers API — nouvelles immatriculations                                    #
# --------------------------------------------------------------------------- #

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=16))
def fetch_pappers_new_companies(date_depuis: str) -> list[dict]:
    """
    Récupère les entreprises immatriculées depuis `date_depuis` (YYYY-MM-DD).
    Doc: https://api.pappers.fr/documentation/v2
    """
    if not PAPPERS_API_KEY:
        log.warning("PAPPERS_API_KEY manquante — utilisation des données mock")
        return _mock_pappers_response()

    params = {
        "api_token": PAPPERS_API_KEY,
        "date_immatriculation_min": date_depuis,
        "precision": "standard",
        "par_page": 50,
        "page": 1,
    }

    resp = httpx.get(
        "https://api.pappers.fr/v2/recherche",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    companies = data.get("resultats", [])
    log.info(f"[Pappers] {len(companies)} nouvelles sociétés trouvées")
    return companies


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=16))
def fetch_sirene_establishment(siret: str) -> Optional[dict]:
    """
    Enrichit les données avec l'API INSEE Sirene v3.
    Doc: https://api.insee.fr/catalogue/site/themes/wso2/subthemes/insee/pages/item-info.jag?name=Sirene&version=V3&provider=insee
    """
    if not SIRENE_API_TOKEN:
        return None

    headers = {"Authorization": f"Bearer {SIRENE_API_TOKEN}"}
    resp = httpx.get(
        f"https://api.insee.fr/entreprises/sirene/V3/siret/{siret}",
        headers=headers,
        timeout=20,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("etablissement", {})


# --------------------------------------------------------------------------- #
# Curation IA — GPT-4                                                         #
# --------------------------------------------------------------------------- #

def generate_ai_insight(company: dict) -> dict:
    """
    Génère un besoin comptable personnalisé pour la société via GPT-4.
    Retourne { aiInsight, accountingNeed, estimatedRevenue }.
    """
    if not openai_client:
        return {
            "aiInsight": "Analyse IA non disponible (clé OpenAI manquante).",
            "accountingNeed": "Tenue comptable standard + déclarations fiscales",
            "estimatedRevenue": 1500,
        }

    name = company.get("nom_entreprise", "Entreprise inconnue")
    naf = company.get("code_naf", "")
    naf_label = company.get("libelle_code_naf", "")
    city = company.get("ville", "")
    legal_form = company.get("forme_juridique", "")

    prompt = f"""Tu es un expert-comptable spécialisé dans la prospection commerciale.
Analyse cette nouvelle entreprise et génère une proposition commerciale concise.

Entreprise : {name}
Forme juridique : {legal_form}
Code NAF : {naf} — {naf_label}
Ville : {city}

Réponds UNIQUEMENT en JSON avec ces 3 champs :
- aiInsight : une phrase d'accroche sur les besoins probables (max 120 caractères)
- accountingNeed : la mission comptable recommandée (max 150 caractères)
- estimatedRevenue : tarif mensuel estimé en EUR (entier entre 800 et 5000)
"""

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=200,
        temperature=0.7,
    )

    content = response.choices[0].message.content or "{}"
    return json.loads(content)


# --------------------------------------------------------------------------- #
# Transformation — Pappers → format MirrorTrace                               #
# --------------------------------------------------------------------------- #

def transform_company(raw: dict, ai_data: dict) -> dict:
    return {
        "siret": raw.get("siret", ""),
        "siren": raw.get("siren", ""),
        "companyName": raw.get("nom_entreprise", ""),
        "directorName": raw.get("dirigeants", [{}])[0].get("nom_complet", "Dirigeant inconnu")
        if raw.get("dirigeants")
        else "Dirigeant inconnu",
        "nafCode": raw.get("code_naf", ""),
        "nafLabel": raw.get("libelle_code_naf", ""),
        "createdAt": raw.get("date_immatriculation", datetime.now().isoformat()),
        "address": raw.get("adresse_ligne_1", ""),
        "city": raw.get("ville", ""),
        "postalCode": raw.get("code_postal", ""),
        "email": raw.get("email", None),
        "phone": raw.get("telephone", None),
        "status": "identified",
        "aiInsight": ai_data.get("aiInsight", ""),
        "accountingNeed": ai_data.get("accountingNeed", ""),
        "estimatedRevenue": ai_data.get("estimatedRevenue", 1500),
        "scrapedAt": datetime.now().isoformat(),
    }


# --------------------------------------------------------------------------- #
# Push vers le dashboard Next.js                                               #
# --------------------------------------------------------------------------- #

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def push_to_dashboard(prospects: list[dict]) -> None:
    """Envoie les nouveaux prospects à l'API Next.js via webhook."""
    if not prospects:
        return

    resp = httpx.post(
        DASHBOARD_WEBHOOK,
        json={"prospects": prospects},
        timeout=15,
        headers={"Content-Type": "application/json", "X-Scraper-Secret": os.getenv("SCRAPER_SECRET", "")},
    )
    resp.raise_for_status()
    log.info(f"[Dashboard] {len(prospects)} prospects envoyés avec succès")


# --------------------------------------------------------------------------- #
# Boucle principale                                                            #
# --------------------------------------------------------------------------- #

def run_scraping_cycle() -> None:
    console.rule("[gold1]MirrorTrace — Cycle de scraping[/gold1]")
    state = load_state()

    date_depuis = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d")
    if state.get("last_run"):
        last = datetime.fromisoformat(state["last_run"])
        date_depuis = last.strftime("%Y-%m-%d")

    log.info(f"Recherche des immatriculations depuis {date_depuis}")

    try:
        companies = fetch_pappers_new_companies(date_depuis)
    except Exception as e:
        log.error(f"Échec Pappers: {e}")
        return

    new_prospects = []
    seen = set(state.get("seen_sirets", []))

    for company in companies:
        siret = company.get("siret", "")
        if not siret or siret in seen:
            continue

        log.info(f"Nouveau SIRET: {siret} — {company.get('nom_entreprise', '')}")

        try:
            ai_data = generate_ai_insight(company)
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"Erreur GPT-4 pour {siret}: {e}")
            ai_data = {"aiInsight": "", "accountingNeed": "", "estimatedRevenue": 1500}

        prospect = transform_company(company, ai_data)
        new_prospects.append(prospect)
        seen.add(siret)

    if new_prospects:
        try:
            push_to_dashboard(new_prospects)
        except Exception as e:
            log.error(f"Échec envoi dashboard: {e}")
            _save_to_local_queue(new_prospects)

    state["seen_sirets"] = list(seen)[-5000:]
    state["last_run"] = datetime.now().isoformat()
    state["total_scraped"] = state.get("total_scraped", 0) + len(new_prospects)
    save_state(state)

    log.info(f"Cycle terminé — {len(new_prospects)} nouveaux / {state['total_scraped']} total")


def _save_to_local_queue(prospects: list[dict]) -> None:
    queue_file = Path("offline_queue.jsonl")
    with queue_file.open("a") as f:
        for p in prospects:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    log.info(f"{len(prospects)} prospects sauvegardés en file locale")


def _mock_pappers_response() -> list[dict]:
    """Données mock pour tests sans clé API."""
    return [
        {
            "siret": f"9999{i:010d}",
            "siren": f"9999{i:05d}",
            "nom_entreprise": f"SOCIÉTÉ TEST {i} SAS",
            "code_naf": "6201Z",
            "libelle_code_naf": "Programmation informatique",
            "ville": "Paris",
            "code_postal": "75001",
            "date_immatriculation": datetime.now().strftime("%Y-%m-%d"),
            "dirigeants": [{"nom_complet": f"Dirigeant Test {i}"}],
            "adresse_ligne_1": f"{i} Rue de la Paix",
        }
        for i in range(1, 4)
    ]


# --------------------------------------------------------------------------- #
# Planification                                                               #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    console.print(
        "\n[bold gold1]MirrorTrace Scraper[/bold gold1] — Surveillance des immatriculations\n",
        justify="center",
    )

    run_scraping_cycle()

    schedule.every(30).minutes.do(run_scraping_cycle)

    log.info("Planificateur actif — cycle toutes les 30 minutes. Ctrl+C pour arrêter.")
    while True:
        schedule.run_pending()
        time.sleep(60)
