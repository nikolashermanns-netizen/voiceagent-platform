"""
Expert Client Wrapper fuer den Bestell-Agent.

Delegiert komplexe Fachfragen an GPT-5/O-Serie Modelle.
"""

import asyncio
import json
import logging
import os
from typing import Callable, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Verfuegbare Experten-Modelle
EXPERT_MODELS = {
    "gpt-5-mini": {"base": "GPT-5", "speed": "fast", "type": "standard", "latency_sec": 10},
    "gpt-5-nano": {"base": "GPT-5", "speed": "fast", "type": "standard", "latency_sec": 24},
    "gpt-5": {"base": "GPT-5", "speed": "medium", "type": "standard", "latency_sec": 27},
    "gpt-5.2": {"base": "GPT-5", "speed": "medium", "type": "standard", "latency_sec": 30},
    "o4-mini": {"base": "O-Serie", "speed": "fast", "type": "reasoning", "latency_sec": 15},
    "o3": {"base": "O-Serie", "speed": "slow", "type": "reasoning", "latency_sec": 30},
    "o3-pro": {"base": "O-Serie", "speed": "slow", "type": "reasoning", "latency_sec": 45},
}

DEFAULT_MODEL = "o4-mini"
DEFAULT_MIN_CONFIDENCE = 0.6

DEFAULT_EXPERT_INSTRUCTIONS = """Du bist ein erfahrener SHK-Fachexperte bei Heinrich Schmidt, einem Fachgrosshandel.

=== DEIN STIL ===
- Verhalte dich menschlich und natuerlich
- Antworte warmherzig und kollegial
- Nutze natuerliche Sprache

=== DEIN ZUGRIFF ===
Du hast Zugriff auf 63 Hersteller im SHK-Bereich:
SANITAER: Grohe, Hansgrohe, Geberit, Duravit, Villeroy & Boch
HEIZUNG: Viessmann, Buderus, Vaillant, Wolf, Junkers
ROHRSYSTEME: Viega (Profipress, Sanpress, Megapress), Geberit (Mapress, Mepla)
PUMPEN: Grundfos, Wilo, Oventrop, Danfoss
WERKZEUGE: Rothenberger, REMS, Knipex, Makita

=== ABLAUF BEI PRODUKTFRAGEN ===
1. Nutze IMMER "suche_produkte" um passende Produkte zu finden!
2. Gib konkrete Produktempfehlungen aus den Suchergebnissen
3. WICHTIG: Suche zuerst, antworte nicht ohne Suche!

=== WICHTIGE REGELN ===
- Bei Produktfragen: IMMER erst suchen mit "suche_produkte"!
- Nenne gefundene Produkte mit Namen (OHNE Artikelnummer)
- Halte Antworten kurz und praegnant (2-3 Saetze)
- Keine Vermutungen - nur gesichertes Fachwissen

=== ANTWORT-FORMAT ===
Du MUSST immer in diesem JSON-Format antworten:
{
    "antwort": "Deine Antwort (kurz, praegnant, fuer Sprachausgabe)",
    "konfidenz": 0.0-1.0,
    "begruendung": "Kurze Begruendung",
    "artikelnummern": ["falls vorhanden"]
}

=== KONFIDENZ-SKALA ===
- 1.0: Absolut sicher, aus Dokumentation bestaetigt
- 0.95: Sehr sicher, Produkt im Katalog gefunden
- 0.9: Sicher, aus Standardwissen
- 0.8: Empfehlung basierend auf Suchergebnissen
- 0.7: Allgemeine Empfehlung ohne exakten Treffer
- 0.5: Beste Vermutung

=== SHK-FACHWISSEN: ROHRSYSTEME ===
TRINKWASSER-GEEIGNET: Temponox (V4A), Sanpress Inox, Profipress, Mapress Edelstahl, Mepla, Sanfix
NUR HEIZUNG/GAS: Megapress, Prestabo, Mapress C-Stahl"""

# Expert Tools fuer Katalog-Zugriff
EXPERT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "suche_produkte",
            "description": "Sucht Produkte im Katalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "suchbegriff": {
                        "type": "string",
                        "description": "Wonach suchst du?"
                    }
                },
                "required": ["suchbegriff"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "zeige_hersteller",
            "description": "Zeigt alle verfuegbaren Hersteller.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]


class ExpertClient:
    """Client fuer Experten-Anfragen an GPT-5 und O-Serie Modelle."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = AsyncOpenAI(api_key=api_key)
        self._enabled_models = list(EXPERT_MODELS.keys())
        self._min_confidence = DEFAULT_MIN_CONFIDENCE
        self._default_model = DEFAULT_MODEL
        self._instructions = DEFAULT_EXPERT_INSTRUCTIONS

        # Callbacks
        self.on_expert_start: Optional[Callable] = None
        self.on_expert_done: Optional[Callable] = None

        # Statistiken
        self._stats = {
            "total_requests": 0,
            "successful": 0,
            "low_confidence": 0,
            "errors": 0,
            "avg_latency_ms": 0,
        }

    @property
    def enabled_models(self) -> list:
        return self._enabled_models.copy()

    @property
    def min_confidence(self) -> float:
        return self._min_confidence

    @property
    def stats(self) -> dict:
        return self._stats.copy()

    def select_model(self, urgency: str) -> str:
        """Waehlt das beste Modell basierend auf Dringlichkeit."""
        enabled = self._enabled_models
        if urgency == "schnell":
            for model in ["gpt-5-mini", "o4-mini", "gpt-5-nano"]:
                if model in enabled:
                    return model
        elif urgency == "gruendlich":
            for model in ["o3-pro", "o3", "gpt-5.2", "gpt-5"]:
                if model in enabled:
                    return model
        else:
            for model in ["o4-mini", "gpt-5", "o3", "gpt-5-mini"]:
                if model in enabled:
                    return model
        return enabled[0] if enabled else self._default_model

    async def ask_expert(
        self, question: str, context: str = "",
        urgency: str = "normal", model: str = None
    ) -> dict:
        """Stellt eine Frage an das Experten-Modell."""
        import time
        start_time = time.time()

        selected_model = model if model and model in self._enabled_models else self.select_model(urgency)
        model_info = EXPERT_MODELS.get(selected_model, {})
        self._stats["total_requests"] += 1

        logger.info(f"[Expert] Frage an {selected_model}: {question[:100]}...")

        if self.on_expert_start:
            try:
                await self.on_expert_start(question, selected_model)
            except Exception as e:
                logger.warning(f"on_expert_start callback error: {e}")

        try:
            messages = [{"role": "system", "content": self._instructions}]
            if context:
                messages.append({"role": "user", "content": f"KONTEXT:\n{context}"})
            messages.append({"role": "user", "content": f"KUNDENFRAGE:\n{question}"})

            response = await self._client.chat.completions.create(
                model=selected_model,
                messages=messages,
                response_format={"type": "json_object"},
                max_completion_tokens=1000
            )

            content = response.choices[0].message.content or "{}"
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                result = {
                    "antwort": content,
                    "konfidenz": 0.5,
                    "begruendung": "Konnte JSON nicht parsen",
                    "artikelnummern": []
                }

            latency_ms = int((time.time() - start_time) * 1000)
            confidence = result.get("konfidenz", 0.0)

            if confidence >= self._min_confidence:
                self._stats["successful"] += 1
                final_result = {
                    "success": True,
                    "antwort": result.get("antwort", ""),
                    "konfidenz": confidence,
                    "model": selected_model,
                    "latency_ms": latency_ms
                }
            else:
                self._stats["low_confidence"] += 1
                final_result = {
                    "success": False,
                    "antwort": "Das kann ich leider nicht sicher beantworten.",
                    "konfidenz": confidence,
                    "model": selected_model,
                    "latency_ms": latency_ms
                }

            if self.on_expert_done:
                try:
                    await self.on_expert_done(final_result)
                except Exception as e:
                    logger.warning(f"on_expert_done callback error: {e}")

            return final_result

        except Exception as e:
            self._stats["errors"] += 1
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[Expert] Fehler: {e}")

            return {
                "success": False,
                "antwort": "Entschuldigung, ich konnte die Frage gerade nicht bearbeiten.",
                "konfidenz": 0.0,
                "model": selected_model,
                "latency_ms": latency_ms,
                "error": str(e)
            }

    def get_config(self) -> dict:
        return {
            "enabled_models": self._enabled_models,
            "default_model": self._default_model,
            "min_confidence": self._min_confidence,
            "available_models": {
                name: {**info, "enabled": name in self._enabled_models}
                for name, info in EXPERT_MODELS.items()
            }
        }

    def set_config(self, config: dict):
        if "enabled_models" in config:
            valid = [m for m in config["enabled_models"] if m in EXPERT_MODELS]
            if valid:
                self._enabled_models = valid
        if "default_model" in config and config["default_model"] in EXPERT_MODELS:
            self._default_model = config["default_model"]
        if "min_confidence" in config:
            self._min_confidence = max(0.5, min(1.0, config["min_confidence"]))
