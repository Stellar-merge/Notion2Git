import asyncio
import hashlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

# Force UTF-8 encoding for stdout and stderr on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add current directory to path just in case
sys.path.append(str(Path(__file__).parent))

from notion_sync.logger import logger, console
from notion_sync.config import load_config, is_configured, write_env_file, ROOT_DIR
from notion_sync.cache import SyncCache
from notion_sync.notion_client import NotionSyncClient
from notion_sync.markdown_converter import MarkdownConverter
from notion_sync.git_manager import GitManager
from notion_sync.utils import (
    sanitize_filename,
    get_output_directory,
    get_page_image_directory,
    get_relative_image_path,
    ensure_page_directories
)

app = typer.Typer(help="Notion to Git Sync CLI - Mirror your Notion database to a Git repository.")

def check_config_or_prompt() -> bool:
    """Checks if configuration is available. If not, prompts the user interactively."""
    if is_configured():
        return True
        
    console.print("[yellow]⚠️ Configuration is missing or incomplete in your environment or .env file.[/yellow]")
    setup_now = typer.confirm("Would you like to set it up interactively now?", default=True)
    
    if not setup_now:
        console.print("[red]Sync cancelled. Please configure your .env file or run with environment variables.[/red]")
        return False
        
    console.print("\n[cyan]🛠️  Interactive Configuration Setup[/cyan]")
    token = typer.prompt("Notion Integration Token", hide_input=True)
    db_id = typer.prompt("Notion Database ID")
    gh_user = typer.prompt("GitHub Username", default="")
    gh_repo = typer.prompt("GitHub Repository Name", default="")
    git_name = typer.prompt("Git Committer Name", default="github-actions[bot]")
    git_email = typer.prompt("Git Committer Email", default="github-actions[bot]@users.noreply.github.com")
    
    download_imgs = typer.confirm("Download images locally?", default=True)
    delete_gh = typer.confirm("Delete files from GitHub if deleted in Notion?", default=True)
    
    write_env_file(
        token=token,
        database_id=db_id,
        github_username=gh_user,
        github_repository=gh_repo,
        git_name=git_name,
        git_email=git_email,
        download_images=download_imgs,
        delete_on_github=delete_gh
    )
    console.print("[green]✓ Configuration saved to .env file successfully![/green]\n")
    return True

def cleanup_empty_dirs(path: Path, root_path: Path):
    """Recursively deletes empty directories from path up to the root path."""
    try:
        if path == root_path or not path.is_dir() or not path.exists():
            return
        # If directory contains nothing or only empty directories
        if not any(path.iterdir()):
            logger.info(f"Removing empty directory: {path.relative_to(root_path)}")
            path.rmdir()
            cleanup_empty_dirs(path.parent, root_path)
    except Exception as e:
        logger.warning(f"Failed to clean up directory {path}: {e}")

def get_content_hash(content: str) -> str:
    """Generates MD5 hash of string content."""
    return hashlib.md5(content.encode("utf-8")).hexdigest()

def build_tree_dict(paths: List[str]) -> Dict[str, Any]:
    """Helper to convert list of paths to nested dictionary tree."""
    tree: Dict[str, Any] = {}
    for path in sorted(paths):
        parts = Path(path).parts
        current = tree
        for part in parts:
            current = current.setdefault(part, {})
    return tree

def render_tree_node(node: Dict[str, Any], prefix: str = "") -> str:
    """Helper to recursively render visual directory tree."""
    lines = []
    keys = list(node.keys())
    for idx, key in enumerate(keys):
        is_last = (idx == len(keys) - 1)
        connector = "└── " if is_last else "├── "
        
        has_children = bool(node[key])
        display_name = key + "/" if has_children else key
        
        lines.append(f"{prefix}{connector}{display_name}")
        
        if has_children:
            extension_prefix = "    " if is_last else "│   "
            lines.append(render_tree_node(node[key], prefix + extension_prefix))
            
    return "\n".join([line for line in lines if line])

def generate_readme_content(cache: SyncCache) -> str:
    """Generates the readme file contents using stats and file list from cache."""
    total_notes = cache.total_notes
    total_code_blocks = cache.total_code_blocks
    last_sync = cache.last_sync or "Never"
    
    # Build list of active files
    active_files = [page["relative_path"] for page in cache.data["pages"].values()]
    tree_dict = build_tree_dict(active_files)
    tree_visual = render_tree_node(tree_dict)
    
    # If tree is empty, provide a fallback
    if not tree_visual:
        tree_visual = "No notes synchronized yet."

    content = f"""# Notion DSA & LeetCode Notes

Mirroring Notion DSA database notes to this GitHub repository. Automatically synchronized using [Notion2Git Sync](https://github.com/google-deepmind/antigravity-ide).

> [!NOTE]
> GitHub version is an exact replica of the Notion database. Please do not edit files here manually as they will be overwritten during sync.

---

### 📊 Sync Stats

| Statistic | Value |
| :--- | :--- |
| **Total Notes** | {total_notes} |
| **Total Code Blocks** | {total_code_blocks} |
| **Last Synchronized** | {last_sync} |

---

### 📂 Directory Structure

```text
{tree_visual}
```

---
*Last Sync: {last_sync}*
"""
    return content

def execute_rebuild_readme(cache: SyncCache, notes_dir: Path):
    """Rebuilds the README.md file in the notes repository."""
    logger.info("Rebuilding README.md with updated stats and folder tree...")
    readme_path = notes_dir / "README.md"
    readme_content = generate_readme_content(cache)
    readme_path.write_text(readme_content, encoding="utf-8")
    logger.info("README.md successfully updated.")

def ensure_notes_repo(config) -> GitManager:
    """Ensures notes_dir exists and is initialized/cloned as a Git repository."""
    notes_dir = config.notes_dir
    notes_dir.mkdir(parents=True, exist_ok=True)
    
    git = GitManager(notes_dir, config.git_name, config.git_email)
    
    if not git.is_repo_initialized():
        logger.info(f"Target directory {notes_dir} is not a Git repository. Setting it up...")
        if config.github_username and config.github_repository:
            repo_input = config.github_repository.strip()
            if repo_input.startswith("http") or repo_input.startswith("git@"):
                remote_url = repo_input
            else:
                remote_url = f"https://github.com/{config.github_username}/{repo_input}.git"
                
            logger.info(f"Attempting to clone target repository: {remote_url}")
            import subprocess
            try:
                result = subprocess.run(
                    ["git", "clone", remote_url, "notes"],
                    cwd=str(ROOT_DIR),
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode == 0:
                    logger.info("Successfully cloned target repository.")
                    return git
                else:
                    logger.warning(f"Clone failed (could be private or not created yet): {result.stderr.strip()}")
            except Exception as e:
                logger.warning(f"Failed to clone: {e}")
                
        # Fallback to local init
        logger.info("Initializing new local Git repository in notes directory...")
        git.run_command(["git", "init"])
        if config.github_username and config.github_repository:
            repo_input = config.github_repository.strip()
            if repo_input.startswith("http") or repo_input.startswith("git@"):
                remote_url = repo_input
            else:
                remote_url = f"https://github.com/{config.github_username}/{repo_input}.git"
            git.run_command(["git", "remote", "add", "origin", remote_url])
            git.run_command(["git", "branch", "-M", "main"])
            
    return git

async def sync_process(force: bool = False, dry_run: bool = False):
    """The core async synchronization process."""
    if not check_config_or_prompt():
        return
        
    config = load_config()
    
    # Initialize cache, client, converter, and git manager
    cache = SyncCache(config.cache_dir)
    client = NotionSyncClient(config.notion_token)
    converter = MarkdownConverter(config.notes_dir, config.download_images)
    git = ensure_notes_repo(config)
    
    # Sync counters
    added_count = 0
    modified_count = 0
    renamed_count = 0
    deleted_count = 0
    unchanged_count = 0
    
    # 1. Fetch all active pages from Notion database
    with Console().status("[bold cyan]Fetching pages from Notion database...", spinner="dots"):
        try:
            pages = client.get_database_pages(config.notion_database_id)
        except Exception as e:
            console.print(f"[red]❌ Failed to fetch database pages: {e}[/red]")
            raise typer.Exit(code=1)
            
    if not pages:
        console.print("[yellow]No pages found in the specified database.[/yellow]")
        
    # Map active pages by ID for quick lookups and resolution
    active_pages_map = {page["id"]: page for page in pages}
    
    # Resolve directory path tree for each active page
    # Maps page_id -> Relative Path
    resolved_paths: Dict[str, Path] = {}
    parent_memo: Dict[str, Path] = {}
    
    for page in pages:
        page_id = page["id"]
        title = sanitize_filename(client.get_page_title(page))
        out_dir = get_output_directory(page, config.notes_dir, client, config.notion_database_id, parent_memo)
        rel_dir = out_dir.relative_to(config.notes_dir)
        resolved_paths[page_id] = rel_dir / f"{title}.md"
        
    # 2. Identify additions, modifications, renames, and deletions
    pages_to_sync: List[Tuple[str, str, Path, str]] = [] # list of (page_id, title, relative_path, last_edited_time)
    deleted_page_ids: Set[str] = set(cache.data["pages"].keys()) - set(active_pages_map.keys())
    
    for page_id, page in active_pages_map.items():
        title = client.get_page_title(page)
        rel_path = resolved_paths[page_id]
        last_edited = page.get("last_edited_time", "")
        
        cached_page = cache.get_page(page_id)
        
        if not cached_page:
            # Added page
            pages_to_sync.append((page_id, title, rel_path, last_edited))
            added_count += 1
        else:
            cached_rel_path = cached_page.get("relative_path", "")
            cached_last_edited = cached_page.get("last_edited_time", "")
            
            # Check for rename/move
            is_renamed = str(rel_path) != cached_rel_path
            
            # Check for edits
            is_modified = last_edited != cached_last_edited
            
            if is_renamed or is_modified or force:
                pages_to_sync.append((page_id, title, rel_path, last_edited))
                if is_renamed:
                    renamed_count += 1
                    # Schedule deletion of the old file path and its associated images if path changed
                    if cached_rel_path and cached_rel_path != str(rel_path):
                        old_file_path = config.notes_dir / cached_rel_path
                        if not dry_run:
                            if old_file_path.exists():
                                logger.info(f"Removing old file (renamed/moved): {cached_rel_path}")
                                old_file_path.unlink()
                            
                            # Clean up old associated images
                            old_images = cached_page.get("images", [])
                            for img_rel in old_images:
                                old_img_path = config.notes_dir / img_rel
                                if old_img_path.exists():
                                    logger.info(f"Removing old associated image: {img_rel}")
                                    old_img_path.unlink()
                                    cleanup_empty_dirs(old_img_path.parent, config.notes_dir)
                                    
                            cleanup_empty_dirs(old_file_path.parent, config.notes_dir)
                elif is_modified:
                    modified_count += 1
            else:
                unchanged_count += 1

    # 3. Synchronize modified / new pages
    if pages_to_sync:
        status_label = "[yellow]Dry run: [/yellow]" if dry_run else ""
        console.print(f"\n{status_label}Processing {len(pages_to_sync)} page changes:")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Downloading notes...", total=len(pages_to_sync))
            
            for page_id, title, rel_path, last_edited in pages_to_sync:
                progress.update(task, description=f"[cyan]Downloading: {title}")
                
                page = active_pages_map[page_id]
                if not dry_run:
                    ensure_page_directories(page, config.notes_dir, client, config.notion_database_id, parent_memo)
                
                # Fetch page blocks recursively
                try:
                    blocks = client.get_block_children_recursive(page_id)
                except Exception as e:
                    logger.error(f"Failed to fetch blocks for page '{title}' ({page_id}): {e}")
                    progress.advance(task)
                    continue
                
                # Convert blocks to Markdown
                markdown_content, code_blocks, downloaded_images = await converter.convert(page_id, title, blocks, config.notes_dir / rel_path)
                content_hash = get_content_hash(markdown_content)
                
                # Compare with cached hash to avoid writing identical content
                cached_page = cache.get_page(page_id)
                cached_hash = cached_page.get("hash", "") if cached_page else ""
                
                if cached_hash == content_hash and not force and cached_page and cached_page.get("relative_path") == str(rel_path):
                    logger.info(f"Content hash matched for '{title}'. Skipping disk write.")
                else:
                    if not dry_run:
                        # Write Markdown file
                        full_output_path = config.notes_dir / rel_path
                        full_output_path.write_text(markdown_content, encoding="utf-8")
                        
                        # Store images downloaded during conversion
                        # Calculate filenames
                        cache.update_page(
                            page_id=page_id,
                            title=title,
                            relative_path=str(rel_path),
                            last_edited_time=last_edited,
                            content_hash=content_hash,
                            code_blocks_count=code_blocks
                        )
                        # Append images list into the page cache dictionary
                        cache.data["pages"][page_id]["images"] = downloaded_images
                        logger.info(f"Wrote file: {rel_path}")
                        
                progress.advance(task)
    else:
        console.print("\n[green]✓ All active pages are up-to-date with local cache.[/green]")

    # 4. Handle Deleted Pages
    if deleted_page_ids and config.delete_on_github:
        console.print(f"\nProcessing {len(deleted_page_ids)} page deletions:")
        for page_id in deleted_page_ids:
            cached_page = cache.get_page(page_id)
            if cached_page:
                cached_rel_path = cached_page.get("relative_path", "")
                title = cached_page.get("title", "Deleted Page")
                
                logger.info(f"Deleting page: {title}")
                deleted_count += 1
                
                if not dry_run:
                    # Delete the Markdown file
                    if cached_rel_path:
                        file_path = config.notes_dir / cached_rel_path
                        if file_path.exists():
                            file_path.unlink()
                            logger.info(f"Deleted file: {cached_rel_path}")
                            # Clean up directory if it's now empty
                            cleanup_empty_dirs(file_path.parent, config.notes_dir)
                            
                    # Clean up associated images
                    associated_images = cached_page.get("images", [])
                    for img_rel in associated_images:
                        img_path = config.notes_dir / img_rel
                        if img_path.exists():
                            img_path.unlink()
                            logger.info(f"Deleted associated image: {img_rel}")
                    
                    # Remove from cache
                    cache.remove_page(page_id)

    # 5. Save changes, update README, and push
    if not dry_run:
        # Save cache
        cache.set_last_sync(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cache.save()
        
        # Rebuild README
        execute_rebuild_readme(cache, config.notes_dir)
        
        # Git commit and push
        if git.has_changes():
            console.print("\n[cyan]🚀 Git: Committing and pushing changes...[/cyan]")
            success = git.commit_and_push("Sync Notion notes")
            if success:
                console.print("[green]✓ Git sync completed successfully![/green]")
            else:
                console.print("[red]❌ Git sync failed. Check warnings/errors above.[/red]")
        else:
            console.print("\n[green]No changes detected for Git commit.[/green]")
    else:
        console.print("\n[yellow]Dry run enabled. No cache updates, disk writes, or git sync operations performed.[/yellow]")

    # 6. Display Summary Table
    summary_table = Table(title="Sync Status Summary", title_justify="left", show_header=True, header_style="bold magenta")
    summary_table.add_column("Category", style="cyan")
    summary_table.add_column("Count", style="green", justify="right")
    summary_table.add_row("Added", str(added_count))
    summary_table.add_row("Modified", str(modified_count))
    summary_table.add_row("Renamed/Moved", str(renamed_count))
    summary_table.add_row("Deleted", str(deleted_count))
    summary_table.add_row("Unchanged", str(unchanged_count))
    console.print("\n", summary_table)


@app.command()
def sync(
    force: bool = typer.Option(False, "--force", "-f", help="Force rebuild all notes, ignoring last modified timestamps."),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Run sync process without writing to disk or pushing to Git.")
):
    """Synchronizes Notion DSA database pages with the Git repository."""
    asyncio.run(sync_process(force=force, dry_run=dry_run))


@app.command()
def status():
    """Prints current configuration and synchronization statistics."""
    config_ok = is_configured()
    
    console.print("[bold cyan]Notion2Git Sync Status[/bold cyan]")
    console.print(f"Configuration set up: {'[green]Yes[/green]' if config_ok else '[red]No[/red]'}")
    
    if config_ok:
        config = load_config()
        console.print(f"Notion Database ID: [magenta]{config.notion_database_id}[/magenta]")
        repo_display = config.github_repository
        if repo_display.startswith("http") or repo_display.startswith("git@"):
            repo_display = repo_display.split("/")[-1].replace(".git", "")
        console.print(f"GitHub Repository: [magenta]{config.github_username}/{repo_display}[/magenta]")
        
    cache = SyncCache(load_config().cache_dir)
    console.print(f"Last synchronized: [yellow]{cache.last_sync or 'Never'}[/yellow]")
    console.print(f"Total notes synced: [green]{cache.total_notes}[/green]")
    console.print(f"Total code blocks: [green]{cache.total_code_blocks}[/green]")
    
    if cache.total_notes > 0:
        console.print("\n[bold cyan]Synced Notes List:[/bold cyan]")
        for page_id, info in cache.data["pages"].items():
            console.print(f"- [green]{info['title']}[/green] ({info['relative_path']})")


@app.command()
def rebuild_readme():
    """Rebuilds the README.md file using information from the sync cache."""
    config = load_config()
    cache = SyncCache(config.cache_dir)
    execute_rebuild_readme(cache, config.notes_dir)


@app.command()
def clean_cache():
    """Clears the local sync cache and resets state."""
    confirm = typer.confirm("Are you sure you want to clear the synchronization cache? This will cause the next sync to download everything.", default=False)
    if confirm:
        cache = SyncCache(load_config().cache_dir)
        cache.clear()
        console.print("[green]Sync cache successfully cleared.[/green]")
    else:
        console.print("Operation cancelled.")


if __name__ == "__main__":
    # If the script is run with no arguments, default to the "sync" command
    if len(sys.argv) == 1:
        sys.argv.append("sync")
    app()
