"""
Produktbereiche mit spezifischem SHK-Fachwissen.

Jeder Bereich hat:
- name: Anzeigename
- keywords: Schluesselwoerter zur Erkennung
- catalogs: Zugehoerige Katalog-Keys
- instructions: Bereichsspezifisches Fachwissen fuer die AI

ABDECKUNG: 109 Kataloge / 157.520 Produkte (100%)
"""

PRODUCT_DOMAINS = {
    "rohrsysteme": {
        "name": "Rohrsysteme und Pressfittings",
        "keywords": [
            "pressfitting", "press", "temponox", "sanpress", "profipress", "megapress",
            "prestabo", "mapress", "mepla", "sanfix", "sanha",
            "bogen", "muffe", "rohr", "fitting", "verschraubung", "uebergangsstueck",
            "uebergangsmuffe", "reduzierstueck", "kappe", "flansch", "winkel",
            "t-stueck", "tstueck", "kupplung",
            "kupfer", "edelstahl", "rotguss", "stahl", "verbundrohr", "mehrschicht",
            "viega", "geberit", "uponor", "rehau", "wavin", "aquatherm", "comap",
        ],
        "catalogs": [
            "edelstahl_press", "cu_press", "viega", "viega_profipress",
            "viega_sanpress", "viega_megapress", "geberit_mapress", "geberit_mepla",
            "uponor", "rehau", "wavin", "aquatherm", "comap"
        ],
        "instructions": """=== FACHWISSEN: ROHRSYSTEME UND PRESSFITTINGS ===

GEWINDE-BEZEICHNUNGEN (WICHTIG!):
- Rp = Innengewinde (zylindrisch) -> Kunde sagt "Innengewinde"
- R = Aussengewinde (konisch) -> Kunde sagt "Aussengewinde"
- G = Flachdichtend (mit Dichtring)

Beispiele:
- "1 Zoll Innengewinde" -> suche "Rp1"
- "3/4 Zoll Aussengewinde" -> suche "R3/4"
- "22mm auf 1 Zoll Innengewinde" -> suche "22 Rp1"

ROHRDIMENSIONEN (mm):
- Standard: 15, 18, 22, 28, 35, 42, 54
- XL-Bereich: 64, 76.1, 88.9, 108

PRESSSYSTEME:
- Temponox = Edelstahl fuer Heizung (nicht Trinkwasser!)
- Sanpress = Kupfer/Rotguss fuer Trinkwasser
- Profipress = Kupfer fuer Heizung
- Megapress = Stahl mit Gewinde (fuer Altbausanierung)
- Mapress/Mepla = Geberit Systeme

SUCHSTRATEGIE:
1. Immer System + Produkttyp + Dimension + Gewinde
2. Beispiel: "temponox verschraubung 22 Rp1"
3. Bei vielen Treffern: Nach Gewindeart fragen (Innen/Aussen)"""
    },

    "armaturen": {
        "name": "Sanitaerarmaturen",
        "keywords": [
            "armatur", "wasserhahn", "mischer", "einhebel", "zweigriff",
            "thermostat", "brause", "handbrause", "kopfbrause",
            "waschtischarmatur", "kuechenarmatur", "duscharmatur", "badewannenarmatur",
            "grohe", "hansgrohe", "hansa", "kludi", "dornbracht", "keuco",
        ],
        "catalogs": [
            "grohe", "hansgrohe", "hansa", "kludi", "dornbracht", "keuco", "schell"
        ],
        "instructions": """=== FACHWISSEN: SANITAERARMATUREN ===

ARMATURTYPEN:
- Einhebelmischer: Ein Hebel fuer Temperatur und Menge
- Zweigriffarmatur: Getrennte Griffe fuer Warm/Kalt
- Thermostat: Automatische Temperaturregelung
- Selbstschluss: Schliesst automatisch
- Sensor/Elektronik: Beruehrungslos

MONTAGEARTEN:
- Aufputz (AP): Sichtbar auf der Wand
- Unterputz (UP): Nur Bedienelemente sichtbar
- Standarmatur: Auf Waschtisch montiert
- Wandarmatur: An der Wand montiert

SUCHSTRATEGIE:
1. Hersteller + Typ + Montage
2. Beispiel: "grohe eurosmart waschtisch"
3. Bei Ersatzteilen: Artikelnummer oder Serienname fragen"""
    },

    "keramik": {
        "name": "Sanitaerkeramik und Bad",
        "keywords": [
            "wc", "toilette", "waschtisch", "waschbecken", "badewanne",
            "duschwanne", "dusche", "spuelkasten", "betaetigungsplatte",
            "duravit", "villeroy", "ideal", "keramag", "laufen", "kaldewei",
        ],
        "catalogs": [
            "duravit", "villeroy_boch", "ideal_standard", "keramag",
            "laufen", "kaldewei", "bette", "geberit", "tece", "koralle",
            "hoesch", "hsk", "sanitaer_komplett"
        ],
        "instructions": """=== FACHWISSEN: SANITAERKERAMIK UND BAD ===

WC-TYPEN:
- Wandhaengend: An der Wand, Spuelkasten in Vorwand
- Stand-WC: Auf dem Boden stehend
- Tiefspueler: Standard (hygienischer)
- Spuelrandlos: Leichter zu reinigen

WASCHTISCH-TYPEN:
- Moebel-Waschtisch: Mit passendem Unterschrank
- Aufsatzwaschtisch: Liegt auf Platte auf
- Handwaschbecken: Klein, fuer Gaeste-WC

SUCHSTRATEGIE:
1. Hersteller + Typ + eventuell Serie
2. Beispiel: "duravit starck 3 waschtisch 60"
3. Bei "Waschtisch" IMMER nachfragen: Armatur oder Becken?"""
    },

    "wc_technik": {
        "name": "WC-Technik und Vorwandinstallation",
        "keywords": [
            "vorwand", "installationselement", "spuelkasten", "unterputz",
            "betaetigungsplatte", "druckerplatte", "sigma", "omega",
            "geberit duofix", "tece", "sanit",
        ],
        "catalogs": [
            "geberit", "tece", "sanit", "friatec", "mepa", "schwab", "wisa"
        ],
        "instructions": """=== FACHWISSEN: WC-TECHNIK ===

VORWANDSYSTEME:
- Geberit Duofix: Marktfuehrer
- TECE: Alternative, modernes Design
- Sanit: Guenstigere Alternative

SPUELKASTEN-TYPEN:
- UP320: Geberit Universal (8cm Tiefe)
- UP720: Geberit fuer geringe Tiefen
- Sigma/Omega: Betaetigungssysteme

SUCHSTRATEGIE:
1. Hersteller + Element-Typ
2. Beispiel: "geberit duofix wc element"
3. Ersatzteile: Spuelkasten-Typ erfragen"""
    },

    "heizung": {
        "name": "Heizung und Kessel",
        "keywords": [
            "kessel", "heizkessel", "brennwert", "therme", "waermepumpe",
            "viessmann", "buderus", "vaillant", "wolf", "junkers",
        ],
        "catalogs": [
            "viessmann", "buderus", "vaillant", "wolf_heizung", "wolf",
            "junkers", "weishaupt", "broetje", "rotex", "bosch", "heizung_komplett"
        ],
        "instructions": """=== FACHWISSEN: HEIZUNG UND KESSEL ===

KESSELTYPEN:
- Brennwertkessel: Hoechste Effizienz
- Kombitherme: Heizung + Warmwasser
- Waermepumpe: Luft-Wasser, Sole-Wasser

SUCHSTRATEGIE:
1. Bei Ersatzteilen: Geraetetyp/Artikelnummer erfragen
2. Bei Neugeraeten: Leistung und Brennstoff klaeren
3. Beispiel: "viessmann vitodens 200 ersatzteil pumpe" """
    },

    "heizkoerper": {
        "name": "Heizkoerper und Flaechenheizung",
        "keywords": [
            "heizkoerper", "radiator", "fussbodenheizung", "thermostatventil",
            "kermi", "purmo", "zehnder",
        ],
        "catalogs": [
            "kermi", "purmo", "zehnder", "oventrop", "danfoss", "heimeier",
            "arbonia", "bemm", "cosmo", "schulte", "heizung_komplett"
        ],
        "instructions": """=== FACHWISSEN: HEIZKOERPER ===

TYP-BEZEICHNUNG: Typ 10/11/20/21/22/33 (Reihen x Konvektoren)

SUCHSTRATEGIE:
1. Typ + Hoehe + Laenge
2. Beispiel: "kermi typ 22 600 1000"
3. Bei Ventilen: Hersteller beachten"""
    },

    "klima": {
        "name": "Klimaanlagen",
        "keywords": [
            "klimaanlage", "klima", "split", "multisplit",
            "daikin", "mitsubishi", "panasonic", "lg",
        ],
        "catalogs": ["daikin", "mitsubishi", "panasonic", "lg"],
        "instructions": """=== FACHWISSEN: KLIMAANLAGEN ===

TYPEN: Split, Multisplit, Monoblock, VRF/VRV

SUCHSTRATEGIE:
1. Hersteller + Kuehlleistung + Typ
2. Beispiel: "daikin 3.5 kw wandgeraet" """
    },

    "pumpen": {
        "name": "Pumpen",
        "keywords": [
            "pumpe", "umwaelzpumpe", "zirkulationspumpe",
            "grundfos", "wilo", "dab",
        ],
        "catalogs": [
            "grundfos", "wilo", "oventrop", "danfoss", "honeywell", "resideo",
            "dab", "lowara", "perma"
        ],
        "instructions": """=== FACHWISSEN: PUMPEN ===

EINBAULAENGE: 130mm oder 180mm (Standard)

SUCHSTRATEGIE:
1. Typ + Einbaulaenge + Anschluss
2. Beispiel: "grundfos alpha2 25-60 180" """
    },

    "regelungstechnik": {
        "name": "Regelungstechnik",
        "keywords": [
            "regler", "stellantrieb", "mischer", "dreiwegeventil",
            "siemens", "esbe", "danfoss", "oventrop",
        ],
        "catalogs": [
            "siemens", "esbe", "meibes", "paw", "caleffi",
            "honeywell", "resideo", "danfoss", "oventrop"
        ],
        "instructions": """=== FACHWISSEN: REGELUNGSTECHNIK ===

SUCHSTRATEGIE:
1. Funktion + Anschluss/Leistung
2. Beispiel: "esbe 3-wege-mischer dn25" """
    },

    "druckhaltung": {
        "name": "Druckhaltung und Sicherheit",
        "keywords": [
            "ausdehnungsgefaess", "sicherheitsventil", "druckminderer",
            "reflex", "flamco", "afriso",
        ],
        "catalogs": ["reflex", "flamco", "afriso", "watts", "caleffi"],
        "instructions": """=== FACHWISSEN: DRUCKHALTUNG ===

AUSDEHNUNGSGEFAESSE:
- Heizung: Rot, 1.5 bar Vordruck
- Trinkwasser: Weiss/blau, 4 bar Vordruck

SUCHSTRATEGIE:
1. Produkt + Volumen/Druck + Anschluss
2. Beispiel: "reflex ausdehnungsgefaess 50 liter" """
    },

    "werkzeuge": {
        "name": "Werkzeuge und Maschinen",
        "keywords": [
            "presse", "pressbacke", "rohrzange", "akkuschrauber",
            "rothenberger", "rems", "makita", "milwaukee", "hilti",
        ],
        "catalogs": [
            "rothenberger", "rems", "ridgid", "knipex", "wera", "wiha",
            "makita", "milwaukee", "bosch_werkzeug", "metabo", "hilti"
        ],
        "instructions": """=== FACHWISSEN: WERKZEUGE ===

PRESSBACKEN: MUESSEN zum System passen! (V, M, TH Kontur)

SUCHSTRATEGIE:
1. Bei Pressbacken: System und Dimension erfragen!
2. Beispiel: "rothenberger pressbacke v 22" """
    },

    "befestigung": {
        "name": "Befestigungstechnik",
        "keywords": [
            "duebel", "schraube", "rohrschelle", "montageschiene",
            "fischer", "hilti",
        ],
        "catalogs": ["fischer", "hilti"],
        "instructions": """=== FACHWISSEN: BEFESTIGUNG ===

SUCHSTRATEGIE:
1. Duebeltyp + Durchmesser + Laenge
2. Beispiel: "fischer duebel 10x80" """
    },

    "wasseraufbereitung": {
        "name": "Wasseraufbereitung",
        "keywords": [
            "filter", "wasserfilter", "enthaertung", "enthaerter",
            "bwt", "gruenbeck", "judo",
        ],
        "catalogs": ["bwt", "gruenbeck", "judo", "syr", "kemper", "honeywell"],
        "instructions": """=== FACHWISSEN: WASSERAUFBEREITUNG ===

SUCHSTRATEGIE:
1. Anwendung und Anschlussgroesse klaeren
2. Beispiel: "gruenbeck boxer 1 zoll" """
    },

    "warmwasser": {
        "name": "Warmwasserbereitung",
        "keywords": [
            "speicher", "warmwasserspeicher", "durchlauferhitzer",
            "stiebel", "eltron", "aeg", "clage",
        ],
        "catalogs": ["stiebel_eltron", "aeg", "clage", "vaillant", "buderus"],
        "instructions": """=== FACHWISSEN: WARMWASSER ===

SUCHSTRATEGIE:
1. Elektrisch oder mit Heizung?
2. Speicher oder Durchlauferhitzer?
3. Beispiel: "stiebel eltron dhe 21" """
    },

    "lueftung": {
        "name": "Lueftung und Ventilatoren",
        "keywords": [
            "luefter", "ventilator", "lueftung", "waermerueckgewinnung",
            "helios", "maico", "systemair",
        ],
        "catalogs": ["helios", "maico", "systemair", "pluggit"],
        "instructions": """=== FACHWISSEN: LUEFTUNG ===

SUCHSTRATEGIE:
1. Anwendung + Volumenstrom/Rohrdurchmesser
2. Beispiel: "helios badluefter 100" """
    },

    "isolierung": {
        "name": "Isolierung und Daemmung",
        "keywords": [
            "isolierung", "daemmung", "armaflex", "rohrisolierung",
            "armacell", "rockwool",
        ],
        "catalogs": ["armacell", "rockwool", "isover"],
        "instructions": """=== FACHWISSEN: ISOLIERUNG ===

SUCHSTRATEGIE:
1. Material + Rohrdurchmesser + Dicke
2. Beispiel: "armaflex 22mm 13mm" """
    },

    "solar": {
        "name": "Solar und Photovoltaik",
        "keywords": [
            "solar", "photovoltaik", "wechselrichter", "solarmodul",
            "sma",
        ],
        "catalogs": ["sma_solar"],
        "instructions": """=== FACHWISSEN: SOLAR ===

SUCHSTRATEGIE:
1. Produkt + Leistung
2. Beispiel: "sma sunny boy 5.0" """
    },

    "kueche": {
        "name": "Kueche und Spuelen",
        "keywords": [
            "spuele", "einbauspuele", "spuelbecken", "kuechenarmatur",
            "franke", "blanco",
        ],
        "catalogs": ["franke", "blanco"],
        "instructions": """=== FACHWISSEN: KUECHE ===

SUCHSTRATEGIE:
1. Hersteller + Beckenzahl + Masse
2. Beispiel: "blanco 1.5 becken 80cm" """
    },
}


def get_domain_by_keyword(text: str) -> str:
    """Erkennt den Produktbereich anhand von Keywords."""
    text_lower = text.lower()
    scores = {}
    for domain_key, domain in PRODUCT_DOMAINS.items():
        score = 0
        for keyword in domain["keywords"]:
            if keyword in text_lower:
                score += len(keyword)
        if score > 0:
            scores[domain_key] = score

    if not scores:
        return None
    return max(scores, key=scores.get)


def get_domain_instructions(domain_key: str) -> str:
    """Gibt das Fachwissen fuer einen Bereich zurueck."""
    domain = PRODUCT_DOMAINS.get(domain_key)
    if domain:
        return domain.get("instructions", "")
    return ""


def get_all_domain_names() -> dict:
    """Gibt alle Bereichsnamen zurueck."""
    return {key: domain["name"] for key, domain in PRODUCT_DOMAINS.items()}
