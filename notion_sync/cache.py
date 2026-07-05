import json
from pathlib import Path
from typing import Dict, Any, Optional
from notion_sync.logger import logger

class SyncCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_file = cache_dir / "sync_cache.json"
        self.data: Dict[str, Any] = {"pages": {}, "last_sync": None}
        self.load()

    def load(self) -> None:
        """Loads cache from disk, initializing if it doesn't exist."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                    # Ensure basic schema exists
                    if "pages" not in self.data:
                        self.data["pages"] = {}
                    if "last_sync" not in self.data:
                        self.data["last_sync"] = None
            else:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self.save()
        except Exception as e:
            logger.error(f"Error loading cache: {e}. Starting with an empty cache.")
            self.data = {"pages": {}, "last_sync": None}

    def save(self) -> None:
        """Saves cache to disk."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Gets cache data for a page ID."""
        return self.data["pages"].get(page_id)

    def update_page(
        self,
        page_id: str,
        title: str,
        relative_path: str,
        last_edited_time: str,
        content_hash: str,
        code_blocks_count: int
    ) -> None:
        """Updates or adds a page record in the cache."""
        self.data["pages"][page_id] = {
            "title": title,
            "relative_path": relative_path,
            "last_edited_time": last_edited_time,
            "hash": content_hash,
            "code_blocks_count": code_blocks_count
        }

    def remove_page(self, page_id: str) -> None:
        """Removes a page from the cache."""
        if page_id in self.data["pages"]:
            del self.data["pages"][page_id]

    def set_last_sync(self, timestamp: str) -> None:
        """Sets the last successful sync timestamp."""
        self.data["last_sync"] = timestamp

    def clear(self) -> None:
        """Clears the cache data and writes to disk."""
        self.data = {"pages": {}, "last_sync": None}
        self.save()

    @property
    def total_notes(self) -> int:
        """Returns the total number of notes in the cache."""
        return len(self.data["pages"])

    @property
    def total_code_blocks(self) -> int:
        """Returns the total number of code blocks across all notes."""
        return sum(page.get("code_blocks_count", 0) for page in self.data["pages"].values())

    @property
    def last_sync(self) -> Optional[str]:
        """Returns the last sync timestamp."""
        return self.data.get("last_sync")
