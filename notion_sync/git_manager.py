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
        """Configures Git user.name and user.email for the local repository if provided."""
        if self.git_name:
            logger.info(f"Configuring Git user.name locally: '{self.git_name}'")
            code, _, err = self.run_command(["git", "config", "local", "user.name", self.git_name])
            if code != 0:
                self.run_command(["git", "config", "user.name", self.git_name])
        else:
            logger.info("Git user.name not specified. Using system/global configuration.")

        if self.git_email:
            logger.info(f"Configuring Git user.email locally: '{self.git_email}'")
            code, _, err = self.run_command(["git", "config", "local", "user.email", self.git_email])
            if code != 0:
                self.run_command(["git", "config", "user.email", self.git_email])
        else:
            logger.info("Git user.email not specified. Using system/global configuration.")

    def has_changes(self) -> bool:
        """Returns True if there are modified, deleted, or untracked changes in the repo."""
        code, stdout, _ = self.run_command(["git", "status", "--porcelain"])
        if code != 0:
            return False
        return len(stdout.strip()) > 0

    def commit_and_push(self, message: str = "Sync Notion") -> bool:
        """
        Adds all changes, commits if there are changes, and pushes to remote.
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
                
        # Configure user locally
        self.configure_user()
        
        # Check if changes exist before staging
        if not self.has_changes():
            logger.info("No modifications detected in Git status. Nothing to commit.")
            return False
            
        # Stage all files
        logger.info("Staging changes: git add .")
        code, _, err = self.run_command(["git", "add", "."])
        if code != 0:
            logger.error(f"Failed to run git add: {err}")
            return False
            
        # Double check changes again
        if not self.has_changes():
            logger.info("No staged changes to commit.")
            return False
            
        # Commit changes
        logger.info(f"Committing changes: git commit -m '{message}'")
        code, _, err = self.run_command(["git", "commit", "-m", message])
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
