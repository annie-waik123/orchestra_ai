import os
import logging
from app.core.config import settings

def get_project_logger(project_id: str) -> logging.Logger:
    """Gets a logger instance configured specifically for this project."""
    logger = logging.getLogger(f"project_{project_id}")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        project_dir = os.path.join(settings.LOGS_DIR, project_id)
        os.makedirs(project_dir, exist_ok=True)
        log_file = os.path.join(project_dir, "run.log")
        
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s] %(message)s'
        )
        fh.setFormatter(formatter)
        
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(sh)
        
    return logger

def add_project_file_handler(project_id: str) -> logging.FileHandler:
    """Dynamically binds a file handler to root and framework loggers for execution logging."""
    project_dir = os.path.join(settings.LOGS_DIR, project_id)
    os.makedirs(project_dir, exist_ok=True)
    log_file = os.path.join(project_dir, "run.log")
    
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s [%(name)s] %(message)s')
    fh.setFormatter(formatter)
    
    # Configure logger levels to allow INFO to pass
    logging.getLogger("orchestra_conductor").setLevel(logging.INFO)
    logging.getLogger("orchestra_agent_framework").setLevel(logging.INFO)
    logging.getLogger("orchestra_project_service").setLevel(logging.INFO)
    
    logging.getLogger("orchestra_conductor").addHandler(fh)
    logging.getLogger("orchestra_agent_framework").addHandler(fh)
    logging.getLogger("orchestra_project_service").addHandler(fh)
    
    return fh

def remove_project_file_handler(fh: logging.FileHandler):
    """Safely cleans up dynamic file logger handler bindings."""
    logging.getLogger("orchestra_conductor").removeHandler(fh)
    logging.getLogger("orchestra_agent_framework").removeHandler(fh)
    logging.getLogger("orchestra_project_service").removeHandler(fh)
    fh.close()
