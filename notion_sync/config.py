import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Path to workspace root
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"

# Load environment variables from .env if it exists
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()

@dataclass
class Config:
    notion_token: str
    notion_database_id: str
    github_username: str
    github_repository: str
    git_name: str
    git_email: str
    download_images: bool = True
    delete_on_github: bool = True
    cache_dir: Path = ROOT_DIR / "cache"
    notes_dir: Path = ROOT_DIR / "notes"
    images_dir: Path = ROOT_DIR / "notes" / "images"

def get_env_or_default(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()

def get_env_bool(key: str, default: bool = True) -> bool:
    val = os.getenv(key, "").lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default

def load_config() -> Config:
    """Loads configuration from environment variables."""
    token = get_env_or_default("NOTION_TOKEN")
    db_id = get_env_or_default("NOTION_DATABASE_ID")
    gh_user = get_env_or_default("NOTES_GITHUB_USERNAME")
    gh_repo = get_env_or_default("NOTES_GITHUB_REPOSITORY")
    
    # We can default Git settings if they are not defined
    git_name = get_env_or_default("GIT_NAME", "github-actions[bot]")
    git_email = get_env_or_default("GIT_EMAIL", "github-actions[bot]@users.noreply.github.com")
    
    download_imgs = get_env_bool("DOWNLOAD_IMAGES", True)
    delete_gh = get_env_bool("DELETE_ON_GITHUB", True)
    
    return Config(
        notion_token=token,
        notion_database_id=db_id,
        github_username=gh_user,
        github_repository=gh_repo,
        git_name=git_name,
        git_email=git_email,
        download_images=download_imgs,
        delete_on_github=delete_gh
    )

def is_configured() -> bool:
    """Checks if the minimal required environment variables are set."""
    config = load_config()
    return bool(config.notion_token and config.notion_database_id)

def write_env_file(
    token: str,
    database_id: str,
    github_username: str,
    github_repository: str,
    git_name: str = "github-actions[bot]",
    git_email: str = "github-actions[bot]@users.noreply.github.com",
    download_images: bool = True,
    delete_on_github: bool = True
) -> None:
    """Writes config values back to the local .env file."""
    content = f"""# Notion to Git Sync Config
NOTION_TOKEN={token}
NOTION_DATABASE_ID={database_id}
NOTES_GITHUB_USERNAME={github_username}
NOTES_GITHUB_REPOSITORY={github_repository}
GIT_NAME={git_name}
GIT_EMAIL={git_email}
DOWNLOAD_IMAGES={str(download_images).lower()}
DELETE_ON_GITHUB={str(delete_on_github).lower()}
"""
    ENV_FILE.write_text(content, encoding="utf-8")
