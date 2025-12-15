"""Tests for distribution calculator."""

from decimal import Decimal

import pytest

from fundcli.calculator import (
    WeightingStrategy,
    calculate_distribution,
    calculate_weight,
)
from fundcli.analyzer import UsageAnalysis, ProjectStats, ExecutableStats
from fundcli.mapper import Project
from fundcli.database import TimePeriod
from datetime import datetime


def make_project(id: str, name: str) -> Project:
    """Create a test project."""
    return Project(
        id=id,
        name=name,
        executables=[id],
    )


def make_project_stats(project: Project, count: int, duration_ns: int = 0, success: int = None) -> ProjectStats:
    """Create test project stats."""
    if success is None:
        success = count
    fail = count - success

    stats = ExecutableStats(
        name=project.id,
        count=count,
        total_duration_ns=duration_ns,
        success_count=success,
        fail_count=fail,
    )

    return ProjectStats(
        project=project,
        executables={project.id: stats},
    )


def make_analysis(project_stats: dict[str, ProjectStats]) -> UsageAnalysis:
    """Create a test usage analysis."""
    total = sum(s.total_count for s in project_stats.values())
    return UsageAnalysis(
        period=TimePeriod.MONTH,
        period_start=datetime(2024, 1, 1),
        period_end=datetime(2024, 1, 31),
        total_commands=total,
        total_executables=len(project_stats),
        executable_stats={},
        project_stats=project_stats,
        unknown_executables={},
    )


class TestCalculateWeight:
    """Test weight calculation."""

    def test_count_weight(self):
        project = make_project("git", "Git")
        stats = make_project_stats(project, count=100)
        weight = calculate_weight(stats, WeightingStrategy.COUNT)
        assert weight == 100.0

    def test_duration_weight(self):
        project = make_project("ffmpeg", "FFmpeg")
        stats = make_project_stats(project, count=10, duration_ns=1_000_000_000)
        weight = calculate_weight(stats, WeightingStrategy.DURATION)
        assert weight == 1_000_000_000.0

    def test_success_weight(self):
        project = make_project("make", "Make")
        # 80% success rate
        stats = make_project_stats(project, count=100, success=80)
        weight = calculate_weight(stats, WeightingStrategy.SUCCESS)
        assert weight == 80.0  # count * (success_rate / 100)


class TestCalculateDistribution:
    """Test distribution calculation."""

    def test_simple_distribution(self):
        """Test basic proportional distribution."""
        git = make_project("git", "Git")
        curl = make_project("curl", "curl")

        analysis = make_analysis({
            "git": make_project_stats(git, count=75),
            "curl": make_project_stats(curl, count=25),
        })

        result = calculate_distribution(
            analysis=analysis,
            total_amount=Decimal("10.00"),
            strategy=WeightingStrategy.COUNT,
            min_amount=Decimal("0.00"),  # No minimum
            max_projects=10,
        )

        assert len(result.recommendations) == 2
        assert result.total_amount == Decimal("10.00")

        # Git should get ~$7.50 (75%)
        git_rec = next(r for r in result.recommendations if r.project.id == "git")
        assert git_rec.amount >= Decimal("7.00")

        # curl should get ~$2.50 (25%)
        curl_rec = next(r for r in result.recommendations if r.project.id == "curl")
        assert curl_rec.amount >= Decimal("2.00")

    def test_minimum_threshold(self):
        """Test that minimum threshold is applied."""
        projects = [
            make_project_stats(make_project("git", "Git"), count=90),
            make_project_stats(make_project("curl", "curl"), count=5),
            make_project_stats(make_project("wget", "wget"), count=5),
        ]

        analysis = make_analysis({s.project.id: s for s in projects})

        result = calculate_distribution(
            analysis=analysis,
            total_amount=Decimal("10.00"),
            strategy=WeightingStrategy.COUNT,
            min_amount=Decimal("1.00"),
            max_projects=10,
        )

        # Small projects should be excluded if below threshold
        # The redistribution should give remaining to top projects
        total_allocated = sum(r.amount for r in result.recommendations)
        assert total_allocated <= Decimal("10.00")

    def test_max_projects(self):
        """Test that max_projects is respected."""
        projects = {
            f"project{i}": make_project_stats(make_project(f"project{i}", f"Project {i}"), count=10)
            for i in range(20)
        }

        analysis = make_analysis(projects)

        result = calculate_distribution(
            analysis=analysis,
            total_amount=Decimal("10.00"),
            strategy=WeightingStrategy.COUNT,
            min_amount=Decimal("0.00"),
            max_projects=5,
        )

        assert len(result.recommendations) <= 5

    def test_empty_analysis(self):
        """Test handling of empty analysis."""
        analysis = make_analysis({})

        result = calculate_distribution(
            analysis=analysis,
            total_amount=Decimal("10.00"),
            strategy=WeightingStrategy.COUNT,
        )

        assert len(result.recommendations) == 0
        assert result.total_amount == Decimal("10.00")
