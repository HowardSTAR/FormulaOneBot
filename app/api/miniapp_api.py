from fastapi import FastAPI
from app.handlers.races import build_next_race_payload

app = FastAPI()

@app.get("/api/next-race")
async def api_next_race():
    payload = build_next_race_payload()
    return payload