from fastapi import FastAPI

app = FastAPI(title="Order Automation Demo")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
