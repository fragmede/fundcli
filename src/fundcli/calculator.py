"""Calculate donation distribution based on usage."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from fundcli.analyzer import UsageAnalysis, ProjectStats
from fundcli.mapper import Project


class WeightingStrategy(Enum):
    """How to weight projects for donation allocation."""
    COUNT = "count"           # Simple frequency count
    DURATION = "duration"     # Weight by total execution time
    SUCCESS = "success"       # Weight by success rate
    COMBINED = "combined"     # Blend of all factors


@dataclass
class DonationRecommendation:
    """A recommended donation to a project."""
    project: Project
    amount: Decimal
    percentage: float
    usage_count: int
    weight: float
    capped_at_minimum: bool = False


@dataclass
class DistributionResult:
    """Complete donation distribution result."""
    total_amount: Decimal
    recommendations: list[DonationRecommendation]
    excluded_projects: list[tuple[Project, str]]  # (project, reason)

    @property
    def allocated_amount(self) -> Decimal:
        """Total amount actually allocated."""
        return sum((r.amount for r in self.recommendations), Decimal("0"))

    @property
    def unallocated_amount(self) -> Decimal:
        """Amount not allocated (if any)."""
        return self.total_amount - self.allocated_amount


def calculate_weight(
    stats: ProjectStats,
    strategy: WeightingStrategy,
    max_duration: int = 1,
) -> float:
    """
    Calculate the weight for a project based on strategy.

    Args:
        stats: Project statistics
        strategy: Weighting strategy to use
        max_duration: Maximum duration in the dataset (for normalization)

    Returns:
        Weight value (higher = more donation)
    """
    match strategy:
        case WeightingStrategy.COUNT:
            return float(stats.total_count)

        case WeightingStrategy.DURATION:
            # Use total duration (more time = more value)
            return float(stats.total_duration_ns)

        case WeightingStrategy.SUCCESS:
            # Weight by count * success rate
            # Projects with higher success contribute more value
            return stats.total_count * (stats.success_rate / 100)

        case WeightingStrategy.COMBINED:
            # Blend: 50% count, 30% duration (normalized), 20% success-weighted count
            count_weight = float(stats.total_count)
            duration_weight = float(stats.total_duration_ns) / max_duration if max_duration > 0 else 0
            success_weight = stats.total_count * (stats.success_rate / 100)

            return 0.5 * count_weight + 0.3 * duration_weight * count_weight + 0.2 * success_weight


@dataclass
class AggregatedRecommendation:
    """Recommendations aggregated by donation URL."""
    url: str
    projects: list[Project]
    total_amount: Decimal
    total_percentage: float
    total_usage_count: int
    any_capped_at_minimum: bool


def aggregate_by_donation_url(
    recommendations: list[DonationRecommendation],
) -> list[AggregatedRecommendation]:
    """
    Group recommendations by primary donation URL, summing amounts.

    Projects sharing the same donation URL (e.g. GNU projects all pointing
    to https://my.fsf.org/donate) get merged into a single entry with
    the combined dollar amount.

    Projects with no donation URL each get their own entry (url="").
    """
    from collections import OrderedDict

    groups: OrderedDict[str, list[DonationRecommendation]] = OrderedDict()
    for rec in recommendations:
        url = rec.project.primary_donation_url or ""
        groups.setdefault(url, []).append(rec)

    result = []
    for url, recs in groups.items():
        result.append(AggregatedRecommendation(
            url=url,
            projects=[r.project for r in recs],
            total_amount=sum((r.amount for r in recs), Decimal("0")),
            total_percentage=sum(r.percentage for r in recs),
            total_usage_count=sum(r.usage_count for r in recs),
            any_capped_at_minimum=any(r.capped_at_minimum for r in recs),
        ))

    # Sort by amount descending
    result.sort(key=lambda a: a.total_amount, reverse=True)
    return result


def calculate_distribution(
    analysis: UsageAnalysis,
    total_amount: Decimal,
    strategy: WeightingStrategy = WeightingStrategy.COUNT,
    min_amount: Decimal = Decimal("1.00"),
    max_projects: int = 10,
) -> DistributionResult:
    """
    Calculate donation distribution across projects.

    Algorithm:
    1. Calculate weights for all projects
    2. Distribute proportionally
    3. Apply minimum threshold
    4. Redistribute sub-threshold amounts
    5. Cap at max_projects

    Args:
        analysis: Usage analysis results
        total_amount: Total donation amount
        strategy: How to weight projects
        min_amount: Minimum donation per project
        max_projects: Maximum number of projects

    Returns:
        DistributionResult with recommendations
    """
    if not analysis.project_stats:
        return DistributionResult(
            total_amount=total_amount,
            recommendations=[],
            excluded_projects=[],
        )

    # Calculate max duration for normalization
    max_duration = max(
        (s.total_duration_ns for s in analysis.project_stats.values()),
        default=1,
    )

    # Calculate weights
    weights: list[tuple[ProjectStats, float]] = []
    for stats in analysis.project_stats.values():
        weight = calculate_weight(stats, strategy, max_duration)
        weights.append((stats, weight))

    # Sort by weight descending
    weights.sort(key=lambda x: x[1], reverse=True)

    # Limit to max_projects
    top_projects = weights[:max_projects]
    excluded = weights[max_projects:]

    # Calculate total weight
    total_weight = sum(w for _, w in top_projects)

    if total_weight == 0:
        return DistributionResult(
            total_amount=total_amount,
            recommendations=[],
            excluded_projects=[(s.project, "zero weight") for s, _ in weights],
        )

    # First pass: proportional distribution
    recommendations: list[DonationRecommendation] = []
    below_threshold: list[tuple[ProjectStats, float, Decimal]] = []

    for stats, weight in top_projects:
        proportion = weight / total_weight
        amount = (total_amount * Decimal(str(proportion))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if amount < min_amount:
            below_threshold.append((stats, weight, amount))
        else:
            recommendations.append(DonationRecommendation(
                project=stats.project,
                amount=amount,
                percentage=proportion * 100,
                usage_count=stats.total_count,
                weight=weight,
            ))

    # Handle below-threshold projects
    excluded_reasons = [(s.project, "below minimum threshold") for s, _, _ in below_threshold]
    excluded_reasons.extend([(s.project, "beyond max projects") for s, _ in excluded])

    # Redistribute below-threshold amounts to top projects
    if below_threshold and recommendations:
        redistribute_amount = sum(a for _, _, a in below_threshold)

        # Add proportionally to existing recommendations
        rec_total_weight = sum(r.weight for r in recommendations)
        if rec_total_weight > 0:
            for rec in recommendations:
                extra = (redistribute_amount * Decimal(str(rec.weight / rec_total_weight))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                rec.amount += extra

    # Apply minimum threshold to any that still fall below
    for rec in recommendations:
        if rec.amount < min_amount:
            rec.amount = min_amount
            rec.capped_at_minimum = True

    # Normalize amounts to not exceed total
    current_total = sum(r.amount for r in recommendations)
    if current_total > total_amount:
        # Scale down proportionally
        scale = total_amount / current_total
        for rec in recommendations:
            rec.amount = (rec.amount * scale).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

    # Final adjustment to hit exact total (add/remove pennies from top)
    final_total = sum(r.amount for r in recommendations)
    diff = total_amount - final_total
    if recommendations and diff != 0:
        recommendations[0].amount += diff

    return DistributionResult(
        total_amount=total_amount,
        recommendations=recommendations,
        excluded_projects=excluded_reasons,
    )
