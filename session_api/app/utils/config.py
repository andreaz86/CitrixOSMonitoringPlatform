import os
import logging
from typing import Optional

# Configurazione del logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("session_api")

class Config:
    # Server configuration
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "8000"))
    DEBUG: bool = os.environ.get("DEBUG", "False").lower() == "true"
    
    # Victoria Metrics configuration
    VICTORIA_METRICS_URL: str = os.environ.get("VICTORIA_METRICS_URL", "http://victoriametrics:8428")
    
    # Log level
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    
    def __init__(self):
        # Set log level
        logger.setLevel(getattr(logging, self.LOG_LEVEL))
        
        if self.DEBUG:
            logger.info("Debug mode is enabled")
            logger.info(f"Configuration: HOST={self.HOST}, PORT={self.PORT}")
            logger.info(f"Victoria Metrics URL: {self.VICTORIA_METRICS_URL}")

# Singleton configuration instance
CONFIG = Config()