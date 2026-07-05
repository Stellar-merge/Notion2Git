# Notion to Git Sync (Notion2Git)

A production-grade, fast, and free synchronization tool that mirrors your Notion database of notes (e.g., DSA and LeetCode) to a separate GitHub repository as Markdown files. 

It dynamically replicates your Notion parent-child database hierarchy, downloads and routes images to localized folder trees, tracks page modifications with a high-performance hash cache, and auto-commits/pushes changes to GitHub.

---

## ✨ Features

- **📂 Hierarchical Folder Mirroring**: Automatically reflects nested databases (sub-databases) and pages as folders (e.g., `notes/Patterns/Arrays.md`). Supports any depth of nesting dynamically without hardcoded names.
- **🖼️ Localized Image Syncing**: Downloads Notion-hosted images and routes them to database-wise `images/` folders (e.g. `notes/Patterns/images/`). In-file markdown links are updated to relative assets (`![](images/diagram.png)`).
- **⚡ Cache-Optimized Change Detection**: Employs an MD5 content hash cache to sync only modified, added, or renamed pages, minimizing disk writes and git churn.
- **🔄 Auto-Rename & Move Tracking**: Detects when pages are renamed or moved to different sub-databases in Notion, cleaning up old files, deleting unused images, pruning empty directories, and updating Git history.
- **🤖 GitHub Actions Support**: Includes a pre-configured CI/CD workflow to sync your notes automatically every hour for free.
- **💻 Sleek Interactive CLI**: Guided setup wizard and logs powered by Typer and Rich.

---

## 🚀 Step-by-Step Setup Guide

Follow this guide to get synchronized in 10 minutes.

### Step 1: Set up the Notion Integration
1. Go to the [Notion Integrations Page](https://www.notion.com/my-integrations) and click **+ New integration**.
2. Give it a name (e.g. `Notion2Git`), select the workspace, and click **Submit**.
3. Under **Secrets**, copy the **Internal Integration Token** (you'll need this for `NOTION_TOKEN`).
4. Go to your Notion App, open the parent **DSA Page**, click the `...` menu in the top right, select **Connections**, click **Add connections**, and search for your integration (`Notion2Git`). Share access.
5. Copy the **Page ID** from your parent page URL:
   * URL format: `https://www.notion.so/DSA-2ea301c6436480b1be51d69c2b49ad55`
   * Your ID is the 32-character string at the end: `2ea301c6436480b1be51d69c2b49ad55`.

### Step 2: Set up your Notes GitHub Repository
Create a **private GitHub repository** (e.g., `Stellar-merge/DSA`) where your compiled markdown notes will live. 

### Step 3: Run the Sync App Locally
The project uses `uv`, a fast Python package installer and manager.

1. **Install uv**:
   * **Windows (PowerShell)**:
     ```powershell
     powershell -c "irm https://astral-sh/uv/install.ps1 | iex"
     ```
   * **macOS/Linux**:
     ```bash
     curl -LsSf https://astral-sh/uv/install.sh | sh
     ```
2. **Setup Workspace**:
   ```bash
   git clone https://github.com/<your-username>/Notion2Git.git
   cd Notion2Git
   uv sync
   ```
3. **Configure Environment**:
   Run the sync command. Since there is no `.env` file yet, the CLI will automatically launch a setup wizard to prompt for your credentials:
   ```bash
   uv run sync.py sync
   ```
   Alternatively, copy `.env.example` to `.env` and fill it in:
   ```ini
   NOTION_TOKEN=ntn_your_notion_token_here
   NOTION_DATABASE_ID=your_notion_page_id_here
   NOTES_GITHUB_USERNAME=your_github_username
   NOTES_GITHUB_REPOSITORY=DSA
   GIT_NAME=github-actions[bot]
   GIT_EMAIL=github-actions[bot]@users.noreply.github.com
   DOWNLOAD_IMAGES=true
   DELETE_ON_GITHUB=true
   ```

---

## 💻 CLI Command Reference

| Command | Usage | Description |
|:---|:---|:---|
| **Sync** | `uv run sync.py sync` | Runs incremental sync, compiles markdown, updates README, and pushes to Git. |
| **Force Sync** | `uv run sync.py sync -f` | Bypasses caching and rebuilds all Markdown notes from scratch. |
| **Dry Run** | `uv run sync.py sync -d` | Previews changes without writing to disk or committing to Git. |
| **Status** | `uv run sync.py status` | Prints sync state, counts, configuration, and tracked file list. |
| **Rebuild README** | `uv run sync.py rebuild-readme` | Re-renders stats table and folder visualization in target README manually. |
| **Clean Cache** | `uv run sync.py clean-cache` | Clears local sync cache metadata. |

---

## 🤖 GitHub Actions hourly Sync Setup

To automate syncing every hour for free:
1. Push this sync app repository to your own GitHub account.
2. In your GitHub repository, go to **Settings** -> **Secrets and variables** -> **Actions**.
3. Create the following **Repository Secrets**:
   * `NOTION_TOKEN`: Your secret Notion token.
   * `NOTION_DATABASE_ID`: The ID of your root Notion page.
   * `NOTES_GITHUB_USERNAME`: Your GitHub username.
   * `NOTES_GITHUB_REPOSITORY`: Your private notes repository name (e.g. `DSA`).
4. Go to the **Actions** tab of your repo, select **Notion to Git Sync**, and click **Run workflow** to trigger it manually, or let it run hourly on the cron trigger.

---

## 🗂️ Target Notes Folder Structure Example

Mirroring will yield the following clean repository layout inside your notes repository:

```text
├── README.md
├── Daa/
│   ├── Job-sequncing w deadlines.md
│   ├── P, NP.md
│   ├── Principle of optimality.md
│   └── images/
│       └── img_1.png
├── Data Structures/
│   ├── Binary Tree.md
│   ├── Graph.md
│   ├── Heap.md
│   └── images/
│       └── img_2.png
└── Patterns/
    ├── Arrays.md
    ├── Sliding Window.md
    ├── Two Pointer.md
    └── images/
        └── img_3.png
```
