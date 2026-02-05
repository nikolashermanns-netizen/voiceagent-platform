"""
Katalog-System Wrapper fuer Bestell-Agent.

Delegiert an das zentrale Katalog-System (catalog-Modul im POC).
Dieser Wrapper wird spaeter durch eine eigenstaendige Implementation ersetzt.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Katalog-Daten (lazy loaded)
_index_data: Optional[dict] = None
_loaded_catalogs: dict = {}
_keyword_index: Optional[dict] = None

# Pfade
KATALOG_BASE_DIR = "/app/data/system_katalog"
INDEX_FILE = os.path.join(KATALOG_BASE_DIR, "_index.json")
KEYWORD_INDEX_FILE = os.path.join(KATALOG_BASE_DIR, "_keyword_index.json")


def load_index() -> bool:
    """Laedt den Katalog-Index."""
    global _index_data, _keyword_index

    try:
        if os.path.exists(INDEX_FILE):
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                _index_data = json.load(f)
            logger.info(f"Katalog-Index geladen: {len(_index_data.get('systems', []))} Systeme")
        else:
            logger.warning(f"Katalog-Index nicht gefunden: {INDEX_FILE}")
            return False

        if os.path.exists(KEYWORD_INDEX_FILE):
            with open(KEYWORD_INDEX_FILE, "r", encoding="utf-8") as f:
                _keyword_index = json.load(f)
            logger.info("Keyword-Index geladen")

        return True
    except Exception as e:
        logger.error(f"Fehler beim Laden des Index: {e}")
        return False


def get_available_manufacturers() -> list[dict]:
    """Gibt alle verfuegbaren Hersteller zurueck."""
    if not _index_data:
        return []

    manufacturers = []
    for system in _index_data.get("systems", []):
        manufacturers.append({
            "key": system.get("file", "").replace(".json", ""),
            "name": system.get("name", ""),
            "produkte": system.get("products", 0),
        })
    return manufacturers


def get_manufacturer_key(name: str) -> Optional[str]:
    """Findet den Katalog-Key fuer einen Hersteller-Namen."""
    if not _index_data:
        return None

    name_lower = name.lower().strip()

    for system in _index_data.get("systems", []):
        key = system.get("file", "").replace(".json", "")
        sys_name = system.get("name", "").lower()

        if name_lower == key or name_lower == sys_name:
            return key
        if name_lower in key or name_lower in sys_name:
            return key

    return None


def activate_catalog(key: str) -> bool:
    """Laedt einen Katalog in den Speicher."""
    if key in _loaded_catalogs:
        return True

    catalog_path = os.path.join(KATALOG_BASE_DIR, f"{key}.json")
    if not os.path.exists(catalog_path):
        logger.warning(f"Katalog nicht gefunden: {catalog_path}")
        return False

    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _loaded_catalogs[key] = data
        products = data.get("products", [])
        logger.info(f"Katalog geladen: {key} ({len(products)} Produkte)")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Laden von Katalog {key}: {e}")
        return False


def search_products(query: str, hersteller_key: str = None,
                    nur_aktive: bool = True, max_results: int = 20) -> list[dict]:
    """Sucht Produkte im Katalog."""
    results = []
    query_lower = query.lower()
    query_parts = query_lower.split()

    catalogs_to_search = {}
    if hersteller_key and hersteller_key in _loaded_catalogs:
        catalogs_to_search = {hersteller_key: _loaded_catalogs[hersteller_key]}
    else:
        catalogs_to_search = _loaded_catalogs

    for key, catalog_data in catalogs_to_search.items():
        products = catalog_data.get("products", [])
        for product in products:
            bezeichnung = product.get("bezeichnung", "").lower()

            # Alle Query-Teile muessen matchen
            if all(part in bezeichnung for part in query_parts):
                results.append({
                    "bezeichnung": product.get("bezeichnung", ""),
                    "artikel": product.get("artikel", ""),
                    "hersteller": key,
                    "einheit": product.get("einheit", ""),
                })

                if len(results) >= max_results:
                    return results

    return results


def search_keyword_index(suchbegriff: str) -> str:
    """Sucht im Keyword-Index nach passenden Katalogen."""
    if not _keyword_index:
        return "Keyword-Index nicht verfuegbar."

    suchbegriff_lower = suchbegriff.lower()
    matches = {}

    for keyword, kataloge in _keyword_index.items():
        if suchbegriff_lower in keyword.lower() or keyword.lower() in suchbegriff_lower:
            for katalog in kataloge:
                if katalog not in matches:
                    matches[katalog] = 0
                matches[katalog] += 1

    if not matches:
        return f"Keine Kataloge fuer '{suchbegriff}' gefunden."

    sorted_matches = sorted(matches.items(), key=lambda x: x[1], reverse=True)
    lines = [f"Kataloge fuer '{suchbegriff}':"]
    for katalog, count in sorted_matches[:10]:
        lines.append(f"  - {katalog} ({count} Treffer)")

    return "\n".join(lines)


def find_catalogs_by_keyword(keyword: str) -> dict:
    """Findet Kataloge die ein Keyword enthalten."""
    if not _keyword_index:
        return {"kataloge": []}

    keyword_lower = keyword.lower()
    matches = set()

    for kw, kataloge in _keyword_index.items():
        if keyword_lower in kw.lower():
            matches.update(kataloge)

    return {"kataloge": list(matches)}


def clear_active_catalogs():
    """Entlaedt alle aktiven Kataloge (z.B. bei Anrufende)."""
    count = len(_loaded_catalogs)
    _loaded_catalogs.clear()
    if count > 0:
        logger.info(f"Aktive Kataloge zurueckgesetzt ({count} entladen)")


def get_catalog_for_ai(key: str, max_products: int = 200) -> str:
    """Gibt Katalog-Daten als String fuer AI zurueck."""
    if key not in _loaded_catalogs:
        return f"Katalog '{key}' nicht geladen."

    data = _loaded_catalogs[key]
    products = data.get("products", [])

    lines = [f"=== KATALOG: {key} ({len(products)} Produkte) ===\n"]

    for product in products[:max_products]:
        bezeichnung = product.get("bezeichnung", "")
        artikel = product.get("artikel", "")
        lines.append(f"- {bezeichnung} | Art: {artikel}")

    if len(products) > max_products:
        lines.append(f"\n... und {len(products) - max_products} weitere")

    return "\n".join(lines)


def analyze_search_specificity(query: str, results: list) -> dict:
    """Analysiert ob Suchergebnisse relevant sind."""
    query_parts = query.lower().split()
    relevant_count = 0

    for result in results:
        bezeichnung = result.get("bezeichnung", "").lower()
        if any(part in bezeichnung for part in query_parts):
            relevant_count += 1

    relevance_ratio = relevant_count / len(results) if results else 0

    return {
        "results_relevant": relevance_ratio > 0.3,
        "relevance_ratio": relevance_ratio,
        "alternative_terms": [] if relevance_ratio > 0.3 else _suggest_alternatives(query),
    }


def _suggest_alternatives(query: str) -> list:
    """Schlaegt alternative Suchbegriffe vor."""
    alternatives = []
    parts = query.lower().split()

    # Vereinfache: Nur den Kern-Suchbegriff verwenden
    if len(parts) > 1:
        alternatives.append(parts[0])
        alternatives.append(parts[-1])

    return alternatives
