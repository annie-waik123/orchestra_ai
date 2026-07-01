import os

class Settings:
    def __init__(self):
        # Base storage directory for JSON files
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.STORAGE_DIR = os.getenv(
            "ORCHESTRA_STORAGE_DIR", 
            os.path.join(project_root, "brain", "storage")
        )
        self.TEST_MODE = os.getenv("ORCHESTRA_TEST_MODE", "false").lower() == "true"

settings = Settings()

# Ensure storage directory exists
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
