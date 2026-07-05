## 📋 CLI Command Reference

### Sync Notes

```bash
uv run sync.py sync
```

- This is the default action when running:

```bash
uv run sync.py
```

#### Options

| Option | Description |
|--------|-------------|
| `--force` or `-f` | Rebuild all Markdown notes from Notion, ignoring the sync cache. |
| `--dry-run` or `-d` | Preview page additions, modifications, renames, and deletions without making any changes or pushing to GitHub. |

---

### Check Sync Status

```bash
uv run sync.py status
```

Displays the current synchronization status, cache information, and any pending changes.

---

### Rebuild README

```bash
uv run sync.py rebuild-readme
```

Regenerates the repository's `README.md` based on the latest synced notes.

---

### Clean Sync Cache

```bash
uv run sync.py clean-cache
```

Deletes the local synchronization cache, forcing the next sync to perform a fresh metadata comparison.

---

## Example Workflow

```bash
# Normal incremental sync
uv run sync.py

# Force a full rebuild
uv run sync.py sync --force

# Preview changes without modifying files
uv run sync.py sync --dry-run

# Check synchronization status
uv run sync.py status

# Regenerate README
uv run sync.py rebuild-readme

# Clear local cache
uv run sync.py clean-cache
```