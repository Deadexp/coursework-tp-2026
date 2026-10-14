from fastapi import FastAPI

app = FastAPI(title="English Learning API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
