#!/usr/bin/env python3
"""
BAckUpper - Simple GitHub Repository Backup Tool
Downloads and saves all GitHub repositories of a user to a configured location.
"""
import sys
import subprocess
from pathlib import Path
import yaml
from github import Github, Auth


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_file = Path(config_path)

    if not config_file.exists():
        print(f"Error: Configuration file '{config_path}' not found.")
        print("Please copy config.yaml.example to config.yaml and fill in your details.")
        sys.exit(1)

    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except yaml.YAMLError as e:
        print(f"Error parsing configuration file: {e}")
        sys.exit(1)


def validate_config(config: dict) -> None:
    """Validate required configuration fields."""
    required_fields = ['github_token', 'backup_path']

    for field in required_fields:
        if not config.get(field):
            print(f"Error: Required field '{field}' is missing or empty in config.yaml")
            sys.exit(1)

    # Validate backup path
    backup_path = Path(config['backup_path'])
    if not backup_path.exists():
        print(f"Backup directory does not exist: {backup_path}")
        create = input("Create it? [y/N]: ").strip().lower()
        if create in ('y', 'yes'):
            backup_path.mkdir(parents=True, exist_ok=True)
            print(f"Created directory: {backup_path}")
        else:
            print("Backup cancelled.")
            sys.exit(0)


def get_all_repositories(token: str, username: str = None):
    """Fetch all repositories for the authenticated GitHub user or specified username."""
    try:
        g = Github(auth=Auth.Token(token))

        if username:
            user = g.get_user(username)
        else:
            user = g.get_user()

        repos = list(user.get_repos())
        return repos
    except Exception as e:
        print(f"Error fetching repositories: {e}")
        sys.exit(1)


def pull_repo(repo, dest: Path) -> bool:
    """Pull latest changes for an existing repository."""
    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=str(dest),
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            if "Already up to date" in output:
                print(f"  [UP-TO-DATE] '{repo.full_name}'")
            else:
                print(f"  [UPDATED]    '{repo.full_name}'")
                if output:
                    print(f"               {output[:200]}")
            return True
        else:
            print(f"  [FAIL] Could not pull '{repo.full_name}'")
            if result.stderr:
                print(f"         Error: {result.stderr.strip()[:200]}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  [FAIL] Timeout pulling '{repo.full_name}' (>5 minutes)")
        return False
    except Exception as e:
        print(f"  [FAIL] Error pulling '{repo.full_name}': {e}")
        return False


def clone_repo(repo, backup_path: Path, use_ssh: bool = False) -> bool:
    """Clone a single repository using git."""
    dest = backup_path / repo.name

    if dest.exists():
        return pull_repo(repo, dest)

    # Choose clone URL based on configuration
    clone_url = repo.ssh_url if use_ssh else repo.clone_url

    try:
        # Simple git clone with progress
        result = subprocess.run(
            ["git", "clone", "--progress", clone_url, str(dest)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            print(f"  [OK]   Cloned '{repo.full_name}'")
            return True
        else:
            print(f"  [FAIL] Could not clone '{repo.full_name}'")
            if result.stderr:
                print(f"         Error: {result.stderr.strip()[:200]}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  [FAIL] Timeout cloning '{repo.full_name}' (>5 minutes)")
        return False
    except Exception as e:
        print(f"  [FAIL] Error cloning '{repo.full_name}': {e}")
        return False


def main():
    """Main entry point."""
    print("=" * 50)
    print("          GitHub Backup Tool (BAckUpper)")
    print("=" * 50)
    print()

    # Load and validate configuration
    config = load_config()
    validate_config(config)

    backup_path = Path(config['backup_path'])
    github_token = config['github_token']
    github_username = config.get('github_username')
    use_ssh = config.get('use_ssh', False)

    # Fetch repository list
    print("Fetching repository list from GitHub...")
    repositories = get_all_repositories(github_token, github_username)

    total = len(repositories)
    print(f"Found {total} repositor{'y' if total == 1 else 'ies'}.\n")

    if total == 0:
        print("Nothing to back up. Exiting.")
        return

    # Clone each repository
    print(f"Starting backup to '{backup_path}'\n")

    cloned_count = 0
    updated_count = 0
    failed_count = 0

    for index, repo in enumerate(repositories, start=1):
        print(f"[{index}/{total}] {repo.full_name}")

        dest = backup_path / repo.name
        existed = dest.exists()
        result = clone_repo(repo, backup_path, use_ssh)

        if result:
            if existed:
                updated_count += 1
            else:
                cloned_count += 1
        else:
            failed_count += 1

    # Summary
    print()
    print("=" * 50)
    print("           Backup Complete!")
    print("=" * 50)
    print(f"Total: {total} | Cloned: {cloned_count} | Pulled/Up-to-date: {updated_count} | Failed: {failed_count}")
    print()


if __name__ == "__main__":
    main()
