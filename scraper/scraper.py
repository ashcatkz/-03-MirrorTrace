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
    # Pas de filtre familleavis — on filtre côté Python après inspection
    params = {
        "where": f'dateparution>="{date_depuis}"',
        "limit": 50,
        "offset": offset,
        "order_by": "dateparution DESC",
    }
    resp = httpx.get(BODACC_URL, params=params, timeout=30,
                     headers={"User-Agent": "MirrorTrace/1.0"})
    resp.raise_for_status()
    data = resp.json()
    # Log le premier enregistrement pour inspecter les champs réels
    results = data.get("results", [])
    if results and offset == 0:
        log.info(f"[BODACC] Champs disponibles: {list(results[0].keys())}")
        log.info(f"[BODACC] Exemple: {json.dumps(results[0], ensure_ascii=False)[:300]}")
    return data

def is_immatriculation(record: dict) -> bool:
    famille = record.get("familleavis_lib", "") or record.get("familleavis", "")
    return "mmatriculat" in famille.lower() or "reation" in famille.lower()

def fetch_all_bodacc(date_depuis: str) -> list[dict]:
    all_records = []
    offset = 0
    MAX_OFFSET = 500
    logged_example = False
    while offset <= MAX_OFFSET:
        try:
            data = fetch_bodacc(date_depuis, offset)
            records = data.get("results", [])
            if not records:
                break
            immatriculations = [r for r in records if is_immatriculation(r)]
            # Log le premier exemple d'immatriculation trouvé
            if immatriculations and not logged_example:
                log.info(f"[BODACC] Exemple immatriculation complète:\n{json.dumps(immatriculations[0], ensure_ascii=False, indent=2)[:1000]}")
                logged_example = True
            all_records.extend(immatriculations)
            log.info(f"[BODACC] offset={offset} — {len(immatriculations)} immatriculations")
            if len(records) < 50:
                break
            offset += 50
            time.sleep(0.5)
        except Exception as e:
            log.error(f"[BODACC] Erreur offset {offset}: {e}")
            break
    log.info(f"[BODACC] Total : {len(all_records)} immatriculations")
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

def deep_find(obj, key: str) -> str:
    """Cherche récursivement une clé dans n'importe quel champ imbriqué ou JSON string."""
    if isinstance(obj, dict):
        if key in obj and isinstance(obj[key], str) and obj[key]:
            return obj[key]
        for v in obj.values():
            r = deep_find(v, key)
            if r:
                return r
    elif isinstance(obj, str):
        try:
            return deep_find(json.loads(obj), key)
        except Exception:
            pass
    elif isinstance(obj, list):
        for item in obj:
            r = deep_find(item, key)
            if r:
                return r
    return ""


def normalize_bodacc(record: dict, enrichment: dict = {}) -> dict:
    # Recherche profonde dans tous les champs imbriqués
    denomination = (
        deep_find(record, "denominationSociale") or
        deep_find(record, "denomination") or
        deep_find(record, "raisonSociale") or
        deep_find(record, "nomCommercial") or ""
    )

    # Dirigeant
    gerant = deep_find(record, "nomGerant") or deep_find(record, "gerant") or ""
    nom_p  = deep_find(record, "nom")
    prenom_p = deep_find(record, "prenom")
    if not gerant and (nom_p or prenom_p):
        gerant = f"{prenom_p} {nom_p}".strip()

    # Adresse
    ville  = deep_find(record, "ville") or deep_find(record, "commune") or deep_find(record, "localite") or f"Dpt {record.get('numerodepartement', '')}"
    cp     = deep_find(record, "codePostal") or deep_find(record, "cp") or ""
    rue    = f"{deep_find(record, 'numeroVoie')} {deep_find(record, 'nomVoie')}".strip()

    # NAF
    naf       = deep_find(record, "codeAPE") or deep_find(record, "activitePrincipale") or deep_find(record, "activite") or ""
    naf       = naf.replace(".", "")
    naf_label = NAF_LABELS.get(naf, deep_find(record, "libelleActivite") or "")

    # Forme juridique
    forme = deep_find(record, "formeJuridique") or deep_find(record, "libelleFormeJuridique") or ""

    # SIREN
    siren = deep_find(record, "siren") or deep_find(record, "numeroIdentifiant") or deep_find(record, "numeroIdentification") or ""
    siren = siren.replace(" ", "")[:9] if siren else ""
    unique_id = (siren + "00001") if (siren and len(siren) == 9) else record.get("id", str(record.get("numeroannonce", "")))

    # Date
    date = deep_find(record, "dateImmatriculation") or record.get("dateparution", datetime.now().strftime("%Y-%m-%d"))

    # Enrichissement annuaire si nom encore vide
    if not denomination and enrichment:
        denomination = enrichment.get("nom_complet") or enrichment.get("nom_raison_sociale") or ""
        dirs = enrichment.get("dirigeants", [])
        if dirs and not gerant:
            d = dirs[0]
            gerant = f"{d.get('prenoms','')} {d.get('nom','')}".strip()
        if not naf:
            matching = enrichment.get("matching_etablissements", [{}])
            etab = matching[0] if matching else {}
            naf = etab.get("activite_principale","").replace(".","")
            naf_label = NAF_LABELS.get(naf, "")

    return {
        "siret":             unique_id,
        "siren":             siren,
        "nom_entreprise":    denomination or f"Société BODACC #{record.get('numeroannonce','')}",
        "dirigeants":        [{"nom_complet": gerant or "Non communiqué"}],
        "code_naf":          naf or "9999Z",
        "libelle_code_naf":  naf_label or "Immatriculation",
        "date_immatriculation": date,
        "adresse_ligne_1":   rue,
        "ville":             ville,
        "code_postal":       cp,
        "forme_juridique":   forme,
        "_source":           "BODACC",
    }
    denomination = (
        record.get("denomination") or
        record.get("denominationSociale") or
        record.get("raisonSociale") or ""
    )
    # Dirigeant / gérant
    gerant = record.get("gerant") or record.get("dirigeant") or ""
    if isinstance(gerant, dict):
        gerant = f"{gerant.get('prenom','')} {gerant.get('nom','')}".strip()

    # Adresse siège
    adresse_siege = record.get("adresseSiege") or record.get("adressePrincipalEtablissement") or {}
    if isinstance(adresse_siege, str):
        try:
            adresse_siege = json.loads(adresse_siege)
        except Exception:
            adresse_siege = {}
    ville   = adresse_siege.get("ville") or adresse_siege.get("commune") or record.get("ville") or f"Dpt {record.get('numerodepartement','')}"
    cp      = adresse_siege.get("codePostal") or adresse_siege.get("cp") or ""
    rue     = adresse_siege.get("numeroVoie","") + " " + adresse_siege.get("nomVoie","")

    # NAF / activité
    naf       = (record.get("activite") or "").replace(".", "")
    naf_label = NAF_LABELS.get(naf, record.get("libelleActivite") or record.get("familleavis_lib") or "")

    # SIRET / SIREN — essayer tous les champs possibles
    siren = ""
    for field in ["numeroIdentifiant", "siren", "numeroImmatriculation", "registre"]:
        v = record.get(field)
        if isinstance(v, str):
            clean = v.replace(" ", "").replace(".", "")
            if clean.isdigit() and len(clean) >= 9:
                siren = clean[:9]
                break
        elif isinstance(v, dict):
            for sub in ["numeroIdentification", "siren", "numeroIdentifiant"]:
                sv = str(v.get(sub, "")).replace(" ", "")
                if sv.isdigit() and len(sv) >= 9:
                    siren = sv[:9]
                    break
            if siren:
                break
    # Fallback : utiliser l'ID BODACC comme identifiant unique
    unique_id = record.get("id", str(record.get("numeroannonce", "")))
    siret = (siren + "00001") if (siren and len(siren) == 9) else unique_id

    # Forme juridique
    forme = record.get("formeJuridique") or ""

    # Date
    date = record.get("dateImmatriculation") or record.get("dateparution") or datetime.now().strftime("%Y-%m-%d")

    # Enrichissement annuaire si dénomination vide
    if not denomination and enrichment:
        matching = enrichment.get("matching_etablissements", [{}])
        etab = matching[0] if matching else {}
        denomination = enrichment.get("nom_complet") or enrichment.get("nom_raison_sociale") or ""
        naf = naf or etab.get("activite_principale","").replace(".","")
        naf_label = naf_label or NAF_LABELS.get(naf,"")
        dirs = enrichment.get("dirigeants",[])
        if dirs and not gerant:
            d = dirs[0]
            gerant = f"{d.get('prenoms','')} {d.get('nom','')}".strip()

    return {
        "siret":             siret,
        "siren":             siren,
        "nom_entreprise":    denomination or f"Société BODACC #{record.get('numeroannonce','')}",
        "dirigeants":        [{"nom_complet": gerant or "Non communiqué"}],
        "code_naf":          naf or "9999Z",
        "libelle_code_naf":  naf_label or "Activité commerciale",
        "date_immatriculation": date,
        "adresse_ligne_1":   rue.strip(),
        "ville":             ville,
        "code_postal":       cp,
        "forme_juridique":   forme,
        "_source":           "BODACC",
    }

def _get_nested(record: dict, *keys: str) -> str:
    """Cherche une valeur dans des champs imbriqués ou plats (casse flexible)."""
    for key in keys:
        val = record.get(key) or record.get(key.lower()) or record.get(key.upper())
        if val and isinstance(val, str):
            return val
        if val and isinstance(val, dict):
            # Essaye d'extraire du dict
            for sub in ["denominationSociale", "denomination", "nom", "raisonSociale"]:
                sv = val.get(sub, "")
                if sv:
                    return sv
    return ""

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
        # Normaliser d'abord — le SIRET/ID est extrait par normalize_bodacc
        company = normalize_bodacc(record)
        unique_id = company.get("siret") or record.get("id", "")

        if not unique_id or unique_id in seen:
            continue

        nom = company.get("nom_entreprise", "")
        log.info(f"  → {unique_id} | {nom[:50]}")

        # Enrichissement optionnel via annuaire-entreprises
        siren = company.get("siren", "")
        if siren and len(siren) == 9:
            try:
                enrichment = enrich_entreprise(siren)
                if enrichment:
                    company = normalize_bodacc(record, enrichment)
                time.sleep(0.2)
            except Exception:
                pass

        ai_data = generate_ai_insight(company)
        new_prospects.append(transform(company, ai_data))
        seen.add(unique_id)
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
