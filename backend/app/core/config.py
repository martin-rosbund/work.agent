import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./workagent.db")
DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
APP_ORIGIN = os.getenv("APP_ORIGIN", "http://localhost:8080").rstrip("/")
SESSION_COOKIE = os.getenv("SESSION_COOKIE", "workagent_session")
OAUTH_COOKIE = os.getenv("OAUTH_COOKIE", "workagent_oauth")
MASTER_KEY_FILE = Path(os.getenv("MASTER_KEY_FILE", "../.secrets/master_key"))
SETUP_TOKEN_FILE = Path(os.getenv("SETUP_TOKEN_FILE", "../.secrets/setup_token"))
MAX_FILE_BYTES = 25 * 1024 * 1024
SUPPORTED_EXTENSIONS = {
    ".md",
    ".txt",
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
}
