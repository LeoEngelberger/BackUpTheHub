# BackUpTheHub

A simple Python tool that downloads and saves all GitHub repositories of a user to a configured location.
It is designed as a easy-to-use backup solution for GitHub repositories. It is not interact as a way to manage 
or interact with repositories, but rather as a one-time backup utility.
Basically I wanted a easy way to clone my stuff to a external drive with the least amount of effort possible.

And yes agents were involved, this is a low effort project afterall...

**_This Tool is intended for personal use only, as it as neither been tested thorughly nor has its security been audited. 
Use at your own risk._**

## Features

- Configuration file-based (no interactive prompts)
- Simple git cloning process
- Supports both HTTPS and SSH authentication
- Skips repositories that already exist

## Installation

1. Clone this repository or download the files
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. Copy the example configuration file:
   ```bash
   cp config.yaml.example config.yaml
   ```

2. Edit `config.yaml` with your settings:
   - `github_token`: Your GitHub Personal Access Token ([create one here](https://github.com/settings/tokens))
   - `backup_path`: Local directory where repositories will be cloned
   - `github_username` (optional): Username to backup (defaults to authenticated user)
   - `use_ssh` (optional): Set to `true` for SSH cloning, `false` for HTTPS (default)

### GitHub Token Scopes

Your token needs:
- `repo` scope for private repositories
- `public_repo` scope for public repositories only

## Usage

Simply run:
```bash
python main.py
```

The tool will:
1. Load configuration from `config.yaml`
2. Fetch all repositories from GitHub
3. Clone each repository to the backup directory
4. Skip repositories that already exist
5. Display a summary when complete

## Example Output

```
==================================================
          GitHub Backup Tool (BAckUpper)
==================================================

Fetching repository list from GitHub...
Found 15 repositories.

Starting backup to '/path/to/backup'

[1/15] username/repo1
  [OK]   Cloned 'username/repo1'
[2/15] username/repo2
  [SKIP] 'repo2' already exists
...

==================================================
           Backup Complete!
==================================================
Total: 15 | Success: 10 | Skipped: 3 | Failed: 2
```

## Requirements

- Python 3.6+
- Git installed and available in PATH
- GitHub Personal Access Token

## Troubleshooting

### "Configuration file not found"
Make sure you've copied `config.yaml.example` to `config.yaml` and filled in your details.

### "Error fetching repositories"
Check that your GitHub token is valid and has the required scopes.

### Clone failures
- For HTTPS: Ensure your token has the correct permissions
- For SSH: Ensure your SSH key is added to GitHub and SSH agent is running

## License

MIT
