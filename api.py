"""FastAPI wrapper so the Lovable dashboard can call the Qiskit BB84 script."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bb84 import simulate_bb84

app = FastAPI(title="Q-SHIELD Qiskit API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/bb84")
def bb84(eve: bool = False, n: int = 200):
    n = min(max(n, 20), 400)  # keep requests fast on free hosting
    return simulate_bb84(n_bits=n,eve_present=eve)
