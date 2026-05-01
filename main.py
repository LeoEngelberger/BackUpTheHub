import os
import sys
import subprocess
import tempfile
import threading
import getpass
from pathlib import Path
from github import Github, Auth

# Path to the Windows OpenSSH client (talks to the ssh-agent service via named pipe)
WINDOWS_SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"


def get_all_repositories(token: str):
    """Fetch all repositories for the authenticated GitHub user."""
    g = Github(auth=Auth.Token(token))
    user = g.get_user()
    repos = list(user.get_repos())
    return repos


def clone_repo(repo, backup_path: Path, agent_env: dict):
    """Clone a single repository via SSH, streaming live progress to the terminal."""
    dest = backup_path / repo.name

    if dest.exists():
        print(f"  [SKIP] '{repo.name}' already exists at destination.")
        return

    stderr_lines: list[str] = []

    def _stream_stderr(pipe):
        """Read stderr char-by-char; handle \\r (progress update) and \\n (new line)."""
        buf = []
        while True:
            ch = pipe.read(1)
            if not ch:
                break
            if ch == "\r":
                line = "".join(buf).strip()
                if line:
                    print(f"\r    {line:<75}", end="", flush=True)
                buf = []
            elif ch == "\n":
                line = "".join(buf).strip()
                if line:
                    print(f"\r    {line:<75}")
                    stderr_lines.append(line)
                buf = []
            else:
                buf.append(ch)
        if buf:
            line = "".join(buf).strip()
            if line:
                print(f"\r    {line:<75}")
                stderr_lines.append(line)

    try:
        process = subprocess.Popen(
            ["git", "clone", "--progress", repo.ssh_url, str(dest)],
            env=agent_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        reader = threading.Thread(target=_stream_stderr, args=(process.stderr,), daemon=True)
        reader.start()
        reader.join(timeout=300)  # 5-minute hard limit

        if reader.is_alive():
            process.kill()
            reader.join(2)
            print(f"\n  [FAIL] Timed out cloning '{repo.full_name}' (>5 min).")
            return

        process.wait()

        if process.returncode != 0:
            err = "\n         ".join(stderr_lines[-5:]) if stderr_lines else "(no output)"
            print(f"\n  [FAIL] Could not clone '{repo.full_name}':\n         {err}")
        else:
            print(f"\r  [OK]   Cloned '{repo.full_name}'{' ' * 60}")

    except Exception as exc:
        print(f"\n  [FAIL] Unexpected error cloning '{repo.full_name}': {exc}")


def start_agent_and_load_key(ssh_key_path: str, passphrase: str) -> dict:
    """
    Load the SSH key into the running Windows ssh-agent service using a
    Python-based askpass helper. Returns an env dict for use with git clone.
    """

    # 1. Verify the Windows ssh-agent service is reachable
    check = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True)
    if check.returncode == 2:
        raise RuntimeError(
            "Cannot connect to the ssh-agent service.\n"
            "Open PowerShell as Administrator and run:\n"
            "  Set-Service ssh-agent -StartupType Automatic\n"
            "  Start-Service ssh-agent"
        )

    # 2. If the key is already loaded, skip adding it
    key_fingerprint_check = subprocess.run(
        ["ssh-keygen", "-l", "-f", ssh_key_path],
        capture_output=True, text=True
    )
    if key_fingerprint_check.returncode == 0:
        fingerprint = key_fingerprint_check.stdout.split()[1]  # e.g. SHA256:xxx
        if fingerprint in check.stdout:
            print("  [OK] Key already loaded in ssh-agent, skipping ssh-add.")
            return _build_git_env()

    # 3. Write passphrase to a temp file; build a Python askpass script and
    #    a .bat launcher (SSH_ASKPASS must be a single executable path).
    fd_pass, pass_file = tempfile.mkstemp(prefix="sshpass_")
    fd_py,   py_file   = tempfile.mkstemp(suffix=".py",  prefix="askpass_")
    fd_bat,  bat_file  = tempfile.mkstemp(suffix=".bat", prefix="askpass_")
    try:
        with os.fdopen(fd_pass, "w", encoding="utf-8") as f:
            f.write(passphrase)

        # The askpass script: read the passphrase file and write it to stdout
        with os.fdopen(fd_py, "w", encoding="utf-8") as f:
            f.write(
                f"import sys\n"
                f"with open({repr(pass_file)}, encoding='utf-8') as fh:\n"
                f"    sys.stdout.write(fh.read())\n"
            )

        # The .bat launcher: calls Python with the askpass script
        with os.fdopen(fd_bat, "w", encoding="utf-8") as f:
            f.write(f'@echo off\n"{sys.executable}" "{py_file}"\n')

        env = os.environ.copy()
        env["SSH_ASKPASS"]         = bat_file
        env["SSH_ASKPASS_REQUIRE"] = "force"
        env["DISPLAY"]             = "unused"  # required on some OpenSSH builds

        result = subprocess.run(
            ["ssh-add", ssh_key_path],
            env=env,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ssh-add failed (wrong passphrase?)\n{result.stderr.strip()}"
            )

        print("  [OK] Key loaded into ssh-agent.")
    finally:
        # Wipe all temp files immediately — passphrase must not linger on disk
        for tmp in (pass_file, py_file, bat_file):
            try:
                os.unlink(tmp)
            except OSError:
                pass

    return _build_git_env()


def _build_git_env() -> dict:
    """Return an env dict that pins git to the Windows OpenSSH client."""
    env = os.environ.copy()
    ssh = WINDOWS_SSH if os.path.exists(WINDOWS_SSH) else "ssh"
    # -o BatchMode=yes       → never prompt for anything (fail instead)
    # -o StrictHostKeyChecking=no → auto-accept new host keys (no hanging prompt)
    env["GIT_SSH_COMMAND"] = f'"{ssh}" -o BatchMode=yes -o StrictHostKeyChecking=no'
    return env


def prompt_path() -> Path:
    """Ask the user for a backup destination and confirm it."""
    while True:
        raw = input("Enter backup destination path: ").strip()
        if not raw:
            print("  Path cannot be empty. Please try again.\n")
            continue

        path = Path(raw)
        confirm = input(f"Confirm path '{path}'? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("  Let's try again.\n")
            continue

        if not path.exists():
            create = input("  Path does not exist. Create it? [y/N]: ").strip().lower()
            if create in ("y", "yes"):
                path.mkdir(parents=True, exist_ok=True)
                print(f"  Directory created: {path}\n")
            else:
                print("  Backup cancelled.")
                raise SystemExit(0)

        return path


def prompt_token() -> str:
    """Ask the user for their GitHub Personal Access Token."""
    token = getpass.getpass("GitHub Personal Access Token (input hidden): ").strip()
    if not token:
        print("  [ERROR] Token cannot be empty. Exiting.")
        raise SystemExit(1)
    return token


if __name__ == "__main__":
    SSH_KEY = r"C:\Users\leo\.ssh\id_ed25519"

    print("=" * 40)
    print("       GitHub Backup Tool")
    print("=" * 40)
    print()

    # 1. Destination path
    backup_path = prompt_path()

    # 2. Passphrase → load key into ssh-agent once
    passphrase = getpass.getpass(f"Passphrase for '{SSH_KEY}' (input hidden): ")
    print("\nLoading SSH key into agent...")
    try:
        agent_env = start_agent_and_load_key(SSH_KEY, passphrase)
    except RuntimeError as exc:
        print(f"  [ERROR] {exc}")
        raise SystemExit(1)
    del passphrase   # don't keep it in memory longer than needed

    # 3. GitHub token (used only to list repos via the API)
    token = prompt_token()

    # 4. Fetch repository list
    print("\nFetching repository list from GitHub...")
    try:
        repositories = get_all_repositories(token)
    except Exception as exc:
        print(f"  [ERROR] Failed to fetch repositories: {exc}")
        raise SystemExit(1)

    total = len(repositories)
    print(f"Found {total} repositor{'y' if total == 1 else 'ies'}.\n")

    if total == 0:
        print("Nothing to back up. Exiting.")
        raise SystemExit(0)

    # 5. Clone each repository using the agent env
    print(f"Starting backup → '{backup_path}'\n")
    for index, repo in enumerate(repositories, start=1):
        print(f"[{index:>{len(str(total))}}/{total}] {repo.full_name}")
        clone_repo(repo, backup_path, agent_env)

    print()
    print("=" * 40)
    print("        Backup Complete!")
    print("=" * 40)
