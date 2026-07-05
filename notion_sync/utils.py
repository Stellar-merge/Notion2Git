import os
import re
import httpx
from pathlib import Path
from typing import Optional, Dict, Tuple, Any
from notion_sync.logger import logger

def sanitize_filename(name: str) -> str:
    """Sanitizes a string to be a safe filename for Windows, macOS, and Linux."""
    if not name:
        return "Untitled"
    # Replace invalid chars with space or remove
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name)
    # Replace multiple spaces/newlines with single space
    sanitized = re.sub(r'\s+', " ", sanitized).strip()
    return sanitized if sanitized else "Untitled"

async def download_image(url: str, output_dir: Path, filename_prefix: str) -> Optional[str]:
    """
    Downloads an image from a URL and saves it to the output_dir.
    Returns the relative path to the image block if successful, or None.
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Avoid downloading if URL is not HTTP/S
        if not url.startswith("http"):
            return None

        # Use httpx client to download
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.warning(f"Failed to download image from {url}: status {response.status_code}")
                return None
            
            # Determine extension from Content-Type or URL
            content_type = response.headers.get("Content-Type", "")
            ext = ".png"
            if "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif "gif" in content_type:
                ext = ".gif"
            elif "svg" in content_type:
                ext = ".svg"
            elif "webp" in content_type:
                ext = ".webp"
            else:
                # Fallback to URL extension
                path_match = re.search(r'\.([a-zA-Z0-9]+)(?:\?|$)', url)
                if path_match:
                    ext = f".{path_match.group(1)}"
            
            filename = f"{filename_prefix}{ext}"
            file_path = output_dir / filename
            
            # Save file
            file_path.write_bytes(response.content)
            logger.debug(f"Downloaded image to {file_path}")
            
            # Return relative path for Markdown referencing
            # e.g., images/block_id.png
            return f"images/{filename}"
            
    except Exception as e:
        logger.error(f"Error downloading image {url}: {e}")
        return None

def get_parent_path(parent_info: Dict[str, Any], client, root_id: str, memo: Dict[str, Path] = None) -> Path:
    """Recursively traverses the parent hierarchy to construct the sub-directory path."""
    if memo is None:
        memo = {}
        
    parent_type = parent_info.get("type")
    if not parent_type:
        return Path("")
        
    if parent_type == "data_source_id":
        parent_type = "database_id"
        parent_id = parent_info.get("database_id")
    else:
        parent_id = parent_info.get(parent_type)
        
    if not parent_id:
        return Path("")
        
    clean_parent_id = parent_id.replace("-", "")
    clean_root_id = root_id.replace("-", "")
    
    if clean_parent_id == clean_root_id:
        return Path("")
        
    if clean_parent_id in memo:
        return memo[clean_parent_id]
        
    try:
        if parent_type == "page_id":
            parent_page = client.execute_with_retry(client.client.pages.retrieve, page_id=clean_parent_id)
            title = client.get_page_title(parent_page)
            safe_title = sanitize_filename(title)
            
            grandparent_info = parent_page.get("parent", {})
            parent_path = get_parent_path(grandparent_info, client, root_id, memo) / safe_title
            memo[clean_parent_id] = parent_path
            return parent_path
            
        elif parent_type == "database_id":
            # Retrieve database details using request API
            parent_db = client.execute_with_retry(client.client.request, path=f"databases/{clean_parent_id}", method="GET")
            title_list = parent_db.get("title", [])
            title = title_list[0].get("plain_text", "Database") if title_list else "Database"
            safe_title = sanitize_filename(title)
            
            grandparent_info = parent_db.get("parent", {})
            parent_path = get_parent_path(grandparent_info, client, root_id, memo) / safe_title
            memo[clean_parent_id] = parent_path
            return parent_path
            
    except Exception as e:
        logger.warning(f"Could not resolve parent {parent_id}: {e}")
        
    return Path("")

def get_output_directory(page: Dict[str, Any], notes_dir: Path, client, root_id: str, memo: Dict[str, Path] = None) -> Path:
    """Computes the destination directory path from the page's parent hierarchy."""
    parent_info = page.get("parent", {})
    parent_path = get_parent_path(parent_info, client, root_id, memo)
    return notes_dir / parent_path

def get_page_image_directory(page: Dict[str, Any], notes_dir: Path, client, root_id: str, memo: Dict[str, Path] = None) -> Path:
    """Computes the target images directory path for a page."""
    out_dir = get_output_directory(page, notes_dir, client, root_id, memo)
    return out_dir / "images"

def get_relative_image_path(page: Dict[str, Any], image_filename: str) -> str:
    """Computes the relative image link path to be written in the markdown file."""
    return f"images/{image_filename}"

def ensure_page_directories(page: Dict[str, Any], notes_dir: Path, client, root_id: str, memo: Dict[str, Path] = None) -> Tuple[Path, Path]:
    """Creates and returns the output directory and image directory for a page."""
    out_dir = get_output_directory(page, notes_dir, client, root_id, memo)
    img_dir = out_dir / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)
    return out_dir, img_dir
