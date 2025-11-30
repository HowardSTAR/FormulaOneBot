from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.handlers.races import build_next_race_payload

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://howardstar.github.io",          # твой GitHub Pages
        "https://howardstar.github.io/FormulaOneBot",  # если проект в подкаталоге
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/next-race")
async def api_next_race():
    return build_next_race_payload()