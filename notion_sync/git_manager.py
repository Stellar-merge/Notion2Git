import subprocess
from pathlib import Path
from typing import Tuple
from notion_sync.logger import logger

class GitManager:
    def __init__(self, repo_path: Path, git_name: str, git_email: str):
        self.repo_path = repo_path
        self.git_name = git_name
        self.git_email = git_email

    def run_command(self, args: list) -> Tuple[int, str, str]:
        """Runs a git command in the repository path and returns status code, stdout, and stderr."""
        try:
            result = subprocess.run(
                args,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except FileNotFoundError:
            return -1, "", "Git executable not found."
        except Exception as e:
            return -1, "", str(e)

    def is_git_installed(self) -> bool:
        code, stdout, _ = self.run_command(["git", "--version"])
        return code == 0

    def is_repo_initialized(self) -> bool:
        git_dir = self.repo_path / ".git"
        return git_dir.exists() and git_dir.is_dir()

    def configure_user(self) -> None:
        """Configures Git user.name and user.email for the local repository if provided, or from global config."""
        name_to_set = self.git_name
        email_to_set = self.git_email

        if not name_to_set:
            code, stdout, _ = self.run_command(["git", "config", "--global", "user.name"])
            if code == 0 and stdout.strip():
                name_to_set = stdout.strip()

        if not email_to_set:
            code, stdout, _ = self.run_command(["git", "config", "--global", "user.email"])
            if code == 0 and stdout.strip():
                email_to_set = stdout.strip()

        if name_to_set:
            logger.info(f"Configuring Git user.name locally: '{name_to_set}'")
            self.run_command(["git", "config", "user.name", name_to_set])
        else:
            logger.warning("Git user.name not specified or found in global config.")

        if email_to_set:
            logger.info(f"Configuring Git user.email locally: '{email_to_set}'")
            self.run_command(["git", "config", "user.email", email_to_set])
        else:
            logger.warning("Git user.email not specified or found in global config.")

    def has_changes(self) -> bool:
        """Returns True if there are modified, deleted, or untracked changes in the repo."""
        code, stdout, _ = self.run_command(["git", "status", "--porcelain"])
        if code != 0:
            return False
        return len(stdout.strip()) > 0

    def commit_and_push(self, message: str = "Sync Notion", allow_empty: bool = True) -> bool:
        """
        Adds all changes, commits (allowing empty commit if no changes exist to ensure contribution activity),
        and pushes to remote.
        Returns True if changes were committed and pushed, False otherwise.
        """
        if not self.is_git_installed():
            logger.error("Git is not installed or not available in PATH.")
            return False
            
        if not self.is_repo_initialized():
            logger.warning("Current workspace is not a Git repository. Initializing new git repo...")
            code, _, err = self.run_command(["git", "init"])
            if code != 0:
                logger.error(f"Failed to initialize Git repository: {err}")
                return False
                
        # Configure user locally (overriding any bot defaults)
        self.configure_user()
        
        # Stage all files
        logger.info("Staging changes: git add .")
        code, _, err = self.run_command(["git", "add", "."])
        if code != 0:
            logger.error(f"Failed to run git add: {err}")
            return False
            
        has_changes = self.has_changes()
        
        if not has_changes and not allow_empty:
            logger.info("No modifications detected in Git status. Nothing to commit.")
            return False
            
        # Commit changes
        commit_args = ["git", "commit"]
        if not has_changes and allow_empty:
            commit_args.append("--allow-empty")
        commit_args.extend(["-m", message])
        
        logger.info(f"Committing changes: {' '.join(commit_args)}")
        code, _, err = self.run_command(commit_args)
        if code != 0:
            logger.error(f"Failed to commit changes: {err}")
            return False
            
        # Push changes to remote
        # We check remote first to see if a remote repository is configured
        code, stdout, _ = self.run_command(["git", "remote"])
        if code != 0 or not stdout.strip():
            logger.warning("No Git remote is configured. Skipping git push. (Changes committed locally).")
            return True
            
        logger.info("Pushing changes to remote: git push")
        # Try to push to current branch or default push
        code, _, err = self.run_command(["git", "push"])
        if code != 0:
            logger.warning(f"Git push failed: {err}. Attempting push with tracking branch...")
            # Fetch current branch
            _, branch, _ = self.run_command(["git", "branch", "--show-current"])
            branch = branch.strip() or "main"
            code, _, err = self.run_command(["git", "push", "--set-upstream", "origin", branch])
            if code != 0:
                logger.error(f"Failed to push changes to remote: {err}")
                return False
                
        logger.info("Successfully pushed changes to GitHub.")
        return True
