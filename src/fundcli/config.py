"""Configuration handling for fundcli."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Use tomllib (3.11+) or tomli as fallback
try:
    import tomllib
except ImportError:
    import tomli as tomllib

from fundcli.calculator import WeightingStrategy
from fundcli.database import TimePeriod


def get_config_dir() -> Path:
    """Get the configuration directory."""
    return Path.home() / ".config" / "fundcli"


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.toml"


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: Path = field(default_factory=lambda: Path.home() / ".local" / "share" / "atuin" / "history.db")


@dataclass
class AnalysisConfig:
    """Analysis configuration."""
    default_period: TimePeriod = TimePeriod.MONTH
    exclude_hostnames: list[str] = field(default_factory=list)
    exclude_executables: list[str] = field(default_factory=list)
    include_builtins: bool = False


@dataclass
class DonationConfig:
    """Donation configuration."""
    default_amount: float = 10.00
    min_per_project: float = 1.00
    max_projects: int = 10
    weighting: WeightingStrategy = WeightingStrategy.COUNT


@dataclass
class Config:
    """Complete configuration."""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    donation: DonationConfig = field(default_factory=DonationConfig)
    custom_mappings: dict[str, str] = field(default_factory=dict)  # exe -> project_id


def load_config(path: Path | None = None) -> Config:
    """
    Load configuration from file.

    Args:
        path: Path to config file. Defaults to ~/.config/fundcli/config.toml

    Returns:
        Config object with loaded values (or defaults if file doesn't exist)
    """
    if path is None:
        path = get_config_path()

    config = Config()

    if not path.exists():
        return config

    with open(path, "rb") as f:
        data = tomllib.load(f)

    # Parse database section
    if "database" in data:
        db_data = data["database"]
        if "path" in db_data:
            config.database.path = Path(db_data["path"]).expanduser()

    # Parse analysis section
    if "analysis" in data:
        analysis_data = data["analysis"]
        if "default_period" in analysis_data:
            config.analysis.default_period = TimePeriod(analysis_data["default_period"])
        if "exclude_hostnames" in analysis_data:
            config.analysis.exclude_hostnames = analysis_data["exclude_hostnames"]
        if "exclude_executables" in analysis_data:
            config.analysis.exclude_executables = analysis_data["exclude_executables"]
        if "include_builtins" in analysis_data:
            config.analysis.include_builtins = analysis_data["include_builtins"]

    # Parse donation section
    if "donation" in data:
        donation_data = data["donation"]
        if "default_amount" in donation_data:
            config.donation.default_amount = float(donation_data["default_amount"])
        if "min_per_project" in donation_data:
            config.donation.min_per_project = float(donation_data["min_per_project"])
        if "max_projects" in donation_data:
            config.donation.max_projects = int(donation_data["max_projects"])
        if "weighting" in donation_data:
            config.donation.weighting = WeightingStrategy(donation_data["weighting"])

    # Parse custom mappings
    if "custom_mappings" in data:
        config.custom_mappings = dict(data["custom_mappings"])

    return config


def get_default_config_content() -> str:
    """Get the default configuration file content as a string."""
    return '''# fundcli configuration
# See: https://github.com/your-repo/fundcli for documentation

[database]
# Path to Atuin history database
# path = "~/.local/share/atuin/history.db"

[analysis]
# Default time period for analysis: day, week, month, year, all
default_period = "month"

# Hostnames to exclude from analysis (useful for work machines)
exclude_hostnames = []

# Executables to exclude from analysis
exclude_executables = []

# Include shell builtins (cd, echo, etc.) in analysis
include_builtins = false

[donation]
# Default donation amount in USD
default_amount = 10.00

# Minimum donation per project (projects below this are excluded)
min_per_project = 1.00

# Maximum number of projects to include
max_projects = 10

# Weighting strategy: count, duration, success, combined
weighting = "count"

[custom_mappings]
# Map custom executables to known projects
# my-python-script = "python"
# internal-tool = "internal"  # Mark as internal to exclude
'''
