# fundcli

Analyze your Atuin command history and donate to the open source projects you actually use.

## What it does

fundcli reads your [Atuin](https://atuin.sh) shell history database, analyzes which command-line tools you use most, and recommends how to distribute donations to open source projects proportionally based on your actual usage.

## Installation

```bash
pip install .
# or for development
pip install -e ".[dev]"
```

## Quick Start

```bash
# See what tools you use most (last month by default)
fundcli analyze

# Get donation recommendations for $10
fundcli recommend --amount 10

# Search for a project
fundcli projects curl

# Show all known projects
fundcli projects --all
```

## Commands

### `fundcli analyze`

Analyze your command usage patterns.

```bash
fundcli analyze                    # Last month (default)
fundcli analyze --period week      # Last week
fundcli analyze --period year      # Last year
fundcli analyze --period all       # All history
fundcli analyze --limit 50         # Show top 50
```

### `fundcli recommend`

Generate donation recommendations based on your usage.

```bash
fundcli recommend --amount 10      # $10 distributed across top projects
fundcli recommend -a 20 -n 5       # $20, max 5 projects
fundcli recommend -a 10 -w duration  # Weight by execution time
fundcli recommend -a 10 --format json  # JSON output
fundcli recommend -a 10 --format markdown  # Markdown output
```

Weighting strategies:
- `count` (default) - More usage = more donation
- `duration` - Longer-running commands weighted higher
- `success` - Successful commands weighted higher
- `combined` - Blend of all factors

### `fundcli projects`

Search or list known open source projects.

```bash
fundcli projects curl      # Search for 'curl'
fundcli projects python    # Search for 'python'
fundcli projects --all     # List all known projects
```

### `fundcli config`

Manage configuration.

```bash
fundcli config --init      # Create default config file
fundcli config --show      # Show current config
fundcli config --path      # Show config file path
```

### `fundcli donate`

Generate donation links with pre-filled amounts where supported.

```bash
fundcli donate --amount 10            # Generate links for $10 total
fundcli donate -a 20 -o report.html   # Save HTML report
fundcli donate -a 10 -o report.md     # Save Markdown report
fundcli donate -a 10 --open           # Open links in browser
```

**Note:** Most donation platforms (GitHub Sponsors, Open Collective) don't support fully automated one-time donations. This command generates pre-filled URLs where possible:
- **Open Collective**: Amount is pre-filled in the donation form ✓
- **GitHub Sponsors**: Links to sponsor page (select amount manually)
- **Direct**: Links to project donation page

### `fundcli stats`

Show database statistics.

```bash
fundcli stats
```

## Configuration

Create a config file at `~/.config/fundcli/config.toml`:

```toml
[database]
path = "~/.local/share/atuin/history.db"

[analysis]
default_period = "month"
exclude_executables = ["cd", "ls"]

[donation]
default_amount = 10.00
min_per_project = 1.00
max_projects = 10
weighting = "count"

[custom_mappings]
# Map custom executables to known projects
my-python-script = "python"
```

## How it works

1. **Reads Atuin history** - Connects to your local SQLite database (read-only)
2. **Parses commands** - Extracts executable names, handles pipes, sudo, etc.
3. **Maps to projects** - Uses curated database of 70+ open source projects
4. **Calculates distribution** - Proportionally allocates based on your chosen weighting
5. **Generates report** - Shows recommended donations with links

## Privacy

- All processing happens locally on your machine
- No data is sent anywhere
- Database is accessed read-only

## Contributing

Project mappings are in `src/fundcli/data/projects.toml`. PRs welcome to add more projects!

## License

MIT
