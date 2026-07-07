"""Minimal FastAPI backend for Nigeria 2.0."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Nigeria 2.0 API", version="0.1.0")

# Allow the frontend (and local dev) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://nigeria2.com",
        "https://www.nigeria2.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"service": "nigeria2-backend", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/hello")
def hello(name: str = "Nigeria"):
    return {"message": f"Hello, {name}!"}
