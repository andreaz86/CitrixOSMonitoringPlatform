import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.utils.config import CONFIG

app = FastAPI(
    title="Session API",
    description="API per interrogare dati di sessione da VictoriaMetrics",
    version="1.0.0"
)

# Configurazione CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In produzione, specificare i domini consentiti
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include i router delle API
app.include_router(api_router, prefix="/api")

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    # Avvio del server
    uvicorn.run(
        "app.main:app",
        host=CONFIG.HOST,
        port=CONFIG.PORT,
        reload=CONFIG.DEBUG
    )