# fundcli

Atuin command history analyzer for open source donations.

## Overview

This app reads your Atuin shell history, analyzes which command-line tools you use most, and recommends donations to open source projects proportionally based on usage.

## Development

- Python 3.11+
- Install: `pip install -e .` or `pip install -e ".[dev]"`
- Run: `python -m fundcli` or `fundcli`
- Test: `pytest`

## Project Structure

```
src/fundcli/
├── cli.py          # Typer CLI commands (analyze, recommend, projects)
├── config.py       # Configuration handling (~/.config/fundcli/config.toml)
├── database.py     # Atuin SQLite database reader
├── parser.py       # Command string → executable name extraction
├── analyzer.py     # Usage aggregation and statistics
├── mapper.py       # Executable → Project mapping
├── calculator.py   # Donation distribution algorithm
└── data/
    └── projects.toml   # Curated project database
```

## Key Algorithms

### Command Parsing (parser.py)
- Split on pipes `|`, `&&`, `||`, `;`
- Strip wrapper commands: sudo, env, time, nohup, nice, watch, xargs
- Extract binary name from paths: `/usr/bin/curl` → `curl`
- Handle relative paths: `./script.py` → `script.py`

### Distribution Calculation (calculator.py)
- Configurable weighting: count, duration, success rate, or combined
- Minimum threshold per project (default $1.00)
- Maximum projects (default 10)
- Redistribute sub-threshold amounts to top projects

## Data Sources

- Atuin history: `~/.local/share/atuin/history.db`
- User config: `~/.config/fundcli/config.toml`
- Project mappings: bundled `projects.toml` + user overrides

## Conventions

- Use `rich` for all terminal output
- Keep functions small and testable
- Type hints on all public functions
- Docstrings for modules and public functions
