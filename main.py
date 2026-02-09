from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from deta import Deta
from openai import OpenAI
from config import OPENAI_API_KEY, DETA_PROJECT_KEY

# Init
app = FastAPI(title="REGINA Backend")
client = OpenAI(api_key=OPENAI_API_KEY)
deta = Deta(DETA_PROJECT_KEY)
events_db = deta.Base("regina_events")


# ---------- MODELLI ----------

class Contesto(BaseModel):
    dominio: str
    luogo: Optional[str] = None
    dispositivo: Optional[str] = None
    progetti_paralleli: Optional[int] = None


class StatoInterno(BaseModel):
    energia: int
    stress: int
    umore: str
    note_soggettive: Optional[str] = None


class EventInput(BaseModel):
    titolo: str
    descrizione: str
    tipo: str
    contesto: Contesto
    stato_interno: StatoInterno


# ---------- LLM HELPER ----------

def extract_patterns(event: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
Sei REGINA – Nodo Pattern.

Analizza questo evento e restituisci SOLO un JSON con:
- pattern_rilevati: lista di stringhe sintetiche
- decisione_suggerita: stringa o null
- warning: stringa o null

Evento:
{event}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    content = response.choices[0].message.content

    # Tentiamo di valutare il JSON in modo sicuro
    import json
    try:
        data = json.loads(content)
    except Exception:
        data = {
            "pattern_rilevati": [],
            "decisione_suggerita": None,
            "warning": "LLM_output_non_parsable"
        }

    return data


# ---------- ENDPOINT: LOG EVENTO ----------

@app.post("/event")
def log_event(event_input: EventInput):
    now = datetime.now(timezone.utc).isoformat()

    base_event = {
        "timestamp": now,
        "tipo": event_input.tipo,
        "titolo": event_input.titolo,
        "descrizione": event_input.descrizione,
        "contesto": event_input.contesto.model_dump(),
        "stato_interno": event_input.stato_interno.model_dump(),
        "outcome": {
            "compilato": False,
            "dopo_giorni": None,
            "risultato": None,
            "tempo_speso": None,
            "soldi_spesi": None,
            "decisione_corretta": None,
            "note_post_mortem": None
        }
    }

    patterns = extract_patterns(base_event)

    full_event = {
        **base_event,
        "pattern_rilevati": patterns.get("pattern_rilevati", []),
        "decisione_suggerita": patterns.get("decisione_suggerita"),
        "warning": patterns.get("warning")
    }

    saved = events_db.put(full_event)

    return {
        "status": "ok",
        "id": saved["key"],
        "event": saved
    }


# ---------- HELPER: CARICA TUTTI GLI EVENTI ----------

def load_all_events() -> List[Dict[str, Any]]:
    res = events_db.fetch()
    items = res.items
    while res.last:
        res = events_db.fetch(last=res.last)
        items.extend(res.items)
    return items


# ---------- ENDPOINT: OVERVIEW REGINA ----------

@app.get("/regina/overview")
def regina_overview():
    events = load_all_events()

    from collections import Counter

    pattern_counter = Counter()
    for e in events:
        for p in e.get("pattern_rilevati", []):
            pattern_counter[p] += 1

    top_patterns = [
        {"nome": name, "conteggio": count}
        for name, count in pattern_counter.most_common(10)
    ]

    warnings = []
    # Esempio semplice: energia bassa + pattern negativi
    low_energy_events = [
        e for e in events
        if e.get("stato_interno", {}).get("energia", 3) <= 2
    ]
    if len(low_energy_events) >= 3:
        warnings.append("Hai preso diverse decisioni con energia molto bassa. Rivedi quelle più critiche.")

    return {
        "totale_eventi": len(events),
        "pattern_top": top_patterns,
        "warning_correnti": warnings
    }


# ---------- ENDPOINT: ALERTS (SINCRONICITÀ / PRE-SEGNALI SEMPLIFICATI) ----------

@app.get("/regina/alerts")
def regina_alerts():
    events = load_all_events()

    # Semplificazione: co-occorrenze di pattern
    from collections import Counter
    import itertools

    pair_counter = Counter()
    pattern_freq = Counter()

    for e in events:
        patterns = list(set(e.get("pattern_rilevati", [])))
        for p in patterns:
            pattern_freq[p] += 1
        for a, b in itertools.combinations(sorted(patterns), 2):
            pair_counter[(a, b)] += 1

    sincronicita = []
    total_events = max(len(events), 1)

    for (a, b), count in pair_counter.items():
        expected = (pattern_freq[a] / total_events) * (pattern_freq[b] / total_events) * total_events
        if expected > 0 and count > expected * 2:  # soglia semplice
            sincronicita.append({
                "pattern_a": a,
                "pattern_b": b,
                "significance": round(count / expected, 2),
                "interpretazione": "Questi pattern emergono insieme più del caso."
            })

    return {
        "sincronicita": sincronicita,
        "note": "Versione semplificata. Sufficiente per iniziare a vedere co-occorrenze."
    }
