"""Analyze command usage patterns."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from fundcli.database import HistoryEntry, TimePeriod, query_history
from fundcli.parser import extract_executables
from fundcli.mapper import ProjectMapper, Project


@dataclass
class ExecutableStats:
    """Statistics for a single executable."""
    name: str
    count: int = 0
    total_duration_ns: int = 0
    success_count: int = 0
    fail_count: int = 0
    first_used: datetime | None = None
    last_used: datetime | None = None

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage (0-100)."""
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.0
        return (self.success_count / total) * 100

    @property
    def avg_duration_ms(self) -> float:
        """Average duration in milliseconds."""
        if self.count == 0:
            return 0.0
        return (self.total_duration_ns / self.count) / 1_000_000


@dataclass
class ProjectStats:
    """Aggregated statistics for a project (may have multiple executables)."""
    project: Project
    executables: dict[str, ExecutableStats] = field(default_factory=dict)

    @property
    def total_count(self) -> int:
        """Total command count across all executables."""
        return sum(s.count for s in self.executables.values())

    @property
    def total_duration_ns(self) -> int:
        """Total duration across all executables."""
        return sum(s.total_duration_ns for s in self.executables.values())

    @property
    def total_success(self) -> int:
        """Total successful commands."""
        return sum(s.success_count for s in self.executables.values())

    @property
    def total_fail(self) -> int:
        """Total failed commands."""
        return sum(s.fail_count for s in self.executables.values())

    @property
    def success_rate(self) -> float:
        """Overall success rate as a percentage."""
        total = self.total_success + self.total_fail
        if total == 0:
            return 0.0
        return (self.total_success / total) * 100


@dataclass
class UsageAnalysis:
    """Complete usage analysis results."""
    period: TimePeriod
    period_start: datetime | None
    period_end: datetime
    total_commands: int
    total_executables: int
    executable_stats: dict[str, ExecutableStats]
    project_stats: dict[str, ProjectStats]
    unknown_executables: dict[str, int]  # exe name -> count

    @property
    def known_count(self) -> int:
        """Count of commands with known projects."""
        return sum(s.total_count for s in self.project_stats.values())

    @property
    def unknown_count(self) -> int:
        """Count of commands with unknown executables."""
        return sum(self.unknown_executables.values())


def analyze_usage(
    mapper: ProjectMapper,
    period: TimePeriod = TimePeriod.MONTH,
    hostname: str | None = None,
    include_builtins: bool = False,
    db_path=None,
) -> UsageAnalysis:
    """
    Analyze command usage over a time period.

    Args:
        mapper: ProjectMapper for exe->project mapping
        period: Time period to analyze
        hostname: Filter by hostname
        include_builtins: Whether to include shell builtins
        db_path: Path to Atuin database

    Returns:
        UsageAnalysis with complete statistics
    """
    # Collect stats
    exe_stats: dict[str, ExecutableStats] = defaultdict(lambda: ExecutableStats(name=""))
    total_commands = 0
    period_start = None
    period_end = datetime.now()

    for entry in query_history(db_path, period, hostname, include_failed=True):
        total_commands += 1

        # Track time range
        if period_start is None or entry.timestamp < period_start:
            period_start = entry.timestamp

        # Extract and count executables
        for exe in extract_executables(entry.command, include_builtins):
            stats = exe_stats[exe]
            if not stats.name:
                stats.name = exe

            stats.count += 1
            stats.total_duration_ns += entry.duration_ns

            if entry.success:
                stats.success_count += 1
            else:
                stats.fail_count += 1

            if stats.first_used is None or entry.timestamp < stats.first_used:
                stats.first_used = entry.timestamp
            if stats.last_used is None or entry.timestamp > stats.last_used:
                stats.last_used = entry.timestamp

    # Group by project
    project_stats: dict[str, ProjectStats] = {}
    unknown: dict[str, int] = {}

    for exe, stats in exe_stats.items():
        project = mapper.get_project_for_executable(exe)

        if project:
            if project.id not in project_stats:
                project_stats[project.id] = ProjectStats(project=project)
            project_stats[project.id].executables[exe] = stats
        else:
            unknown[exe] = stats.count

    return UsageAnalysis(
        period=period,
        period_start=period_start,
        period_end=period_end,
        total_commands=total_commands,
        total_executables=len(exe_stats),
        executable_stats=dict(exe_stats),
        project_stats=project_stats,
        unknown_executables=unknown,
    )


def get_top_executables(
    analysis: UsageAnalysis,
    limit: int = 20,
) -> list[tuple[str, ExecutableStats]]:
    """Get top executables by count."""
    sorted_stats = sorted(
        analysis.executable_stats.items(),
        key=lambda x: x[1].count,
        reverse=True,
    )
    return sorted_stats[:limit]


def get_top_projects(
    analysis: UsageAnalysis,
    limit: int = 10,
) -> list[tuple[str, ProjectStats]]:
    """Get top projects by total command count."""
    sorted_stats = sorted(
        analysis.project_stats.items(),
        key=lambda x: x[1].total_count,
        reverse=True,
    )
    return sorted_stats[:limit]
