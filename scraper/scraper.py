"""
MirrorTrace — Scraper BODACC (source officielle des immatriculations)
bodacc-datadila.opendatasoft.com — 100% gratuit, sans clé, sans inscription
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

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
STATE_FILE        = Path(__file__).parent / "scraper_state.json"

openai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        pass

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
# SOURCE — BODACC (Journal officiel des immatriculations)                     #
# Aucune clé, aucune inscription, données officielles                         #
# --------------------------------------------------------------------------- #

BODACC_URL = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=16))
def fetch_bodacc(date_depuis: str, offset: int = 0) -> dict:
    # familleavis est le champ correct dans le dataset BODACC
    params = {
        "where": f'familleavis="Immatriculation" AND dateparution>="{date_depuis}"',
        "limit": 50,
        "offset": offset,
        "order_by": "dateparution DESC",
    }
    resp = httpx.get(BODACC_URL, params=params, timeout=30,
                     headers={"User-Agent": "MirrorTrace/1.0"})
    resp.raise_for_status()
    return resp.json()

def fetch_all_bodacc(date_depuis: str) -> list[dict]:
    all_records = []
    offset = 0
    while True:
        try:
            data = fetch_bodacc(date_depuis, offset)
            records = data.get("results", [])
            if not records:
                break
            all_records.extend(records)
            log.info(f"[BODACC] offset={offset} — {len(records)} annonces")
            if len(records) < 50:
                break
            offset += 50
            time.sleep(0.5)
        except Exception as e:
            log.error(f"[BODACC] Erreur offset {offset}: {e}")
            break
    log.info(f"[BODACC] Total : {len(all_records)} annonces d'immatriculation")
    return all_records

# --------------------------------------------------------------------------- #
# SOURCE 2 — Enrichissement via annuaire-entreprises (par SIRET/SIREN)        #
# --------------------------------------------------------------------------- #

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
def enrich_entreprise(siren: str) -> dict:
    resp = httpx.get(
        f"https://recherche-entreprises.api.gouv.fr/search?q={siren}&page=1&per_page=1",
        timeout=10,
        headers={"User-Agent": "MirrorTrace/1.0"},
    )
    if resp.status_code != 200:
        return {}
    results = resp.json().get("results", [])
    return results[0] if results else {}

# --------------------------------------------------------------------------- #
# Normalisation BODACC → MirrorTrace                                          #
# --------------------------------------------------------------------------- #

NAF_LABELS = {
    "6201Z": "Programmation informatique",
    "6202A": "Conseil systèmes informatiques",
    "7022Z": "Conseil affaires et management",
    "7490B": "Activités spécialisées diverses",
    "6920Z": "Activités comptables",
    "7311Z": "Agences de publicité",
    "4791A": "Vente à distance",
    "5610A": "Restauration traditionnelle",
    "4120A": "Construction maisons individuelles",
    "7010Z": "Activités des sièges sociaux",
    "7112B": "Ingénierie et études techniques",
}

def normalize_bodacc(record: dict, enrichment: dict = {}) -> dict:
    # Données BODACC
    registre = record.get("registre", "")
    siren = record.get("numeroImmatriculation", {}).get("numeroIdentification", "") if isinstance(record.get("numeroImmatriculation"), dict) else ""

    # Personnemorale ou personnePhysique
    personne_morale = record.get("personnePhysique", {}) or {}
    personne_physique = record.get("personnePhysique", {}) or {}
    denomination = (
        record.get("personneMorale", {}) or {}
    ).get("denominationSociale", "")

    if not denomination:
        pm = record.get("personneMorale") or {}
        denomination = pm.get("denominationSociale", "") or pm.get("denomination", "")

    if not denomination:
        pp = record.get("personnePhysique") or {}
        prenom = pp.get("prenom", "")
        nom = pp.get("nom", "")
        denomination = f"{prenom} {nom}".strip() or "Entreprise inconnue"

    # Adresse
    adresse = record.get("adresse", {}) or {}
    ville = adresse.get("ville", "") or adresse.get("commune", "")
    cp = adresse.get("codePostal", "")
    rue = f"{adresse.get('numeroVoie', '')} {adresse.get('typeVoie', '')} {adresse.get('nomVoie', '')}".strip()

    # Enrichissement depuis annuaire-entreprises
    naf = ""
    naf_label = ""
    dirigeant = "Dirigeant non communiqué"

    if enrichment:
        matching = enrichment.get("matching_etablissements", [{}])
        etab = matching[0] if matching else {}
        naf = etab.get("activite_principale", "").replace(".", "")
        naf_label = NAF_LABELS.get(naf, etab.get("libelle_activite_principale", ""))
        dirigeants = enrichment.get("dirigeants", [])
        if dirigeants:
            d = dirigeants[0]
            dirigeant = f"{d.get('prenoms', '')} {d.get('nom', '')}".strip()

    date_pub = record.get("dateparution", datetime.now().strftime("%Y-%m-%d"))

    return {
        "siret":             siren + "00001" if siren and len(siren) == 9 else siren,
        "siren":             siren,
        "nom_entreprise":    denomination,
        "dirigeants":        [{"nom_complet": dirigeant}],
        "code_naf":          naf or "9999Z",
        "libelle_code_naf":  naf_label or "Activité commerciale",
        "date_immatriculation": date_pub,
        "adresse_ligne_1":   rue,
        "ville":             ville,
        "code_postal":       cp,
        "forme_juridique":   (record.get("personneMorale") or {}).get("formeJuridique", ""),
        "_source":           "BODACC",
    }

# --------------------------------------------------------------------------- #
# Analyse IA                                                                   #
# --------------------------------------------------------------------------- #

FALLBACK = {
    "62": ("Startup tech — besoin urgent en comptabilité SaaS.", "Comptabilité analytique + TVA + liasse fiscale", 2200),
    "70": ("Société de conseil — gestion honoraires et missions.", "Tenue mensuelle + TVA + bilan + optimisation IS", 1800),
    "69": ("Activité libérale — déclarations BNC.", "Comptabilité BNC + URSSAF + liasse 2035", 1200),
    "73": ("Agence créative — facturation clients et freelances.", "Comptabilité projets + facturation récurrente", 1500),
    "56": ("Restaurant — gestion caisses et TVA restauration.", "Comptabilité commerce + TVA 10% + paie", 1400),
    "41": ("BTP — suivi chantiers et retenues de garantie.", "Comptabilité BTP + situations travaux", 2000),
    "47": ("Commerce — gestion stocks et TVA.", "Comptabilité commerce + stocks + TVA", 1300),
    "85": ("Formation — gestion des conventions.", "Comptabilité formation + TVA exonérée", 1100),
}

def get_fallback(naf: str) -> dict:
    prefix = naf[:2] if naf else ""
    if prefix in FALLBACK:
        insight, need, rev = FALLBACK[prefix]
    else:
        insight = "Nouvelle société — besoin en structuration comptable."
        need = "Tenue mensuelle + déclarations TVA + bilan annuel"
        rev = 1500
    return {"aiInsight": insight, "accountingNeed": need, "estimatedRevenue": rev}

def generate_ai_insight(company: dict) -> dict:
    if not openai_client:
        return get_fallback(company.get("code_naf", ""))
    try:
        from openai import OpenAI
        prompt = f"""Expert-comptable senior. Analyse cette nouvelle entreprise.
Entreprise : {company.get('nom_entreprise')}
Forme : {company.get('forme_juridique')}
NAF : {company.get('code_naf')} — {company.get('libelle_code_naf')}
Ville : {company.get('ville')}
JSON: aiInsight (120 car.), accountingNeed (150 car.), estimatedRevenue (800-5000)"""
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=200,
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        log.warning(f"GPT erreur: {e}")
        return get_fallback(company.get("code_naf", ""))

# --------------------------------------------------------------------------- #
# Transform                                                                    #
# --------------------------------------------------------------------------- #

def transform(raw: dict, ai: dict) -> dict:
    directors = raw.get("dirigeants", [])
    director = directors[0].get("nom_complet", "Dirigeant inconnu") if directors else "Dirigeant inconnu"
    return {
        "id":               raw.get("siret") or str(time.time()),
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
        "status":           "identified",
        "aiInsight":        ai.get("aiInsight", ""),
        "accountingNeed":   ai.get("accountingNeed", ""),
        "estimatedRevenue": ai.get("estimatedRevenue", 1500),
        "scrapedAt":        datetime.now().isoformat(),
        "source":           "BODACC",
    }

# --------------------------------------------------------------------------- #
# Push                                                                         #
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
    f = Path(__file__).parent / "offline_queue.jsonl"
    with f.open("a", encoding="utf-8") as fh:
        for p in prospects:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

# --------------------------------------------------------------------------- #
# Cycle principal                                                              #
# --------------------------------------------------------------------------- #

def run_cycle() -> None:
    console.rule("[gold1]MirrorTrace — Cycle BODACC[/gold1]")
    state = load_state()
    seen  = set(state.get("seen_sirets", []))

    # Toujours chercher sur les 7 derniers jours minimum
    date_depuis = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    log.info(f"Immatriculations depuis : {date_depuis}")

    records = fetch_all_bodacc(date_depuis)
    if not records:
        log.warning("Aucune annonce BODACC trouvée pour cette période")

    new_prospects = []
    for record in records:
        # Extraire le SIREN
        immat = record.get("numeroImmatriculation")
        siren = ""
        if isinstance(immat, dict):
            siren = immat.get("numeroIdentification", "")
        elif isinstance(immat, str):
            siren = immat

        siret = siren + "00001" if siren and len(siren) == 9 else siren
        if not siret or siret in seen:
            continue

        # Enrichir avec annuaire-entreprises
        enrichment = {}
        if siren:
            try:
                enrichment = enrich_entreprise(siren)
                time.sleep(0.2)
            except Exception:
                pass

        company = normalize_bodacc(record, enrichment)
        nom = company.get("nom_entreprise", "")
        log.info(f"  → {siret} | {nom[:50]}")

        ai_data = generate_ai_insight(company)
        new_prospects.append(transform(company, ai_data))
        seen.add(siret)
        time.sleep(0.1)

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
        f"[gold1]{len(new_prospects)} nouveaux[/gold1] / {state['total_scraped']} total"
    )

# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    console.print("\n[bold gold1]  MirrorTrace Scraper — BODACC  [/bold gold1]\n", justify="center")
    console.print(f"Source  : [green]BODACC officiel ✓ (sans clé)[/green]")
    console.print(f"GPT-4   : {'[green]✓ activé[/green]' if openai_client else '[yellow]absent → fallback NAF[/yellow]'}")
    console.print()

    run_cycle()

    schedule.every(30).minutes.do(run_cycle)
    log.info("Planificateur actif — toutes les 30 min. Ctrl+C pour arrêter.")
    while True:
        schedule.run_pending()
        time.sleep(60)
