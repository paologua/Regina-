from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client
import os

# Carica variabili ambiente
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

class Event(BaseModel):
    titolo: str
    descrizione: str
    tipo: str
    contesto: dict
    stato_interno: dict

@app.post("/event")
def create_event(event: Event):
    data = {
        "titolo": event.titolo,
        "descrizione": event.descrizione,
        "tipo": event.tipo,
        "contesto": event.contesto,
        "stato_interno": event.stato_interno,
    }

    result = supabase.table("events").insert(data).execute()
    return {"status": "ok", "result": result.data}
