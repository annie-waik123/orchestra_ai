import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Orchestra AI API"
    PROJECT_DESCRIPTION: str = "Production API wrapper for the Orchestra AI autonomous software engineering platform."
    PROJECT_VERSION: str = "1.0.0"
    
    # Storage dir matches Project Brain
    STORAGE_DIR: str = os.getenv(
        "ORCHESTRA_STORAGE_DIR", 
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "brain", "storage")
    )
    
    # Workspace root logs folder
    LOGS_DIR: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs"
    )

settings = Settings()

# Ensure directories exist
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.LOGS_DIR, exist_ok=True)
