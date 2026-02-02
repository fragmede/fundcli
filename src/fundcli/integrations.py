"""
Donation platform integrations.

Note: Most donation platforms (GitHub Sponsors, Open Collective) do not support
programmatic one-time donations via API. This module generates pre-filled URLs
that users can click to complete donations manually.

Research findings (Dec 2025):
- GitHub Sponsors: createSponsorship mutation does not work for one-time payments
- Open Collective: Creating contributions with payment providers not supported via API
- Thanks.dev: No public API for direct donations; dependency-tree based distribution

The recommended approach is URL generation + link opening.
"""

from decimal import Decimal
from urllib.parse import urlencode, quote
from dataclasses import dataclass

from fundcli.calculator import DistributionResult, DonationRecommendation, aggregate_by_donation_url
from fundcli.mapper import Project, DonationURL


@dataclass
class DonationLink:
    """A generated donation link with metadata."""
    project_name: str
    platform: str
    url: str
    amount: Decimal
    is_prefilled: bool = False  # Whether the amount is pre-filled in the URL


def generate_opencollective_url(
    collective_slug: str,
    amount: Decimal,
    interval: str = "one-time",
) -> str:
    """
    Generate a pre-filled Open Collective donation URL.

    Args:
        collective_slug: The collective's URL slug (e.g., "curl", "webpack")
        amount: Donation amount in USD
        interval: "one-time" or "month" or "year"

    Returns:
        Pre-filled donation URL

    Example:
        https://opencollective.com/curl/donate?amount=5.00&interval=one-time
    """
    base_url = f"https://opencollective.com/{collective_slug}/donate"
    params = {
        "amount": str(amount),
        "interval": interval,
    }
    return f"{base_url}?{urlencode(params)}"


def generate_github_sponsors_url(
    username_or_org: str,
    amount: Decimal | None = None,
) -> str:
    """
    Generate a GitHub Sponsors URL.

    Note: GitHub Sponsors doesn't support pre-filled amounts for one-time donations.
    The user will select the amount on the sponsors page.

    Args:
        username_or_org: GitHub username or organization
        amount: Ignored (not supported by GitHub)

    Returns:
        GitHub Sponsors URL
    """
    # GitHub Sponsors doesn't support amount pre-fill for one-time
    return f"https://github.com/sponsors/{username_or_org}"


def extract_platform_info(donation_url: DonationURL) -> tuple[str, str]:
    """
    Extract platform and identifier from a donation URL.

    Returns:
        (platform, identifier) tuple
    """
    url = donation_url.url

    if "opencollective.com" in url:
        # Extract slug: https://opencollective.com/curl -> "curl"
        parts = url.rstrip("/").split("/")
        slug = parts[-1] if parts[-1] not in ("donate", "") else parts[-2]
        return ("opencollective", slug)

    elif "github.com/sponsors" in url:
        # Extract username: https://github.com/sponsors/bagder -> "bagder"
        parts = url.rstrip("/").split("/")
        return ("github_sponsors", parts[-1])

    else:
        # Unknown platform, return as-is
        return ("direct", url)


def generate_donation_links(
    distribution: DistributionResult,
) -> list[DonationLink]:
    """
    Generate donation links for all recommended projects, aggregated by URL.

    Projects sharing the same donation URL (e.g. GNU projects pointing to
    https://my.fsf.org/donate) are combined into a single link with the
    summed amount.

    Args:
        distribution: Distribution result from calculator

    Returns:
        List of DonationLink objects with pre-filled URLs where possible
    """
    aggregated = aggregate_by_donation_url(distribution.recommendations)
    links = []

    for agg in aggregated:
        if not agg.url:
            continue

        # Use the first project's donation URL to determine platform
        first_project = agg.projects[0]
        donation_url = first_project.donation_urls[0]
        platform, identifier = extract_platform_info(donation_url)

        names = ", ".join(p.name for p in agg.projects)

        if platform == "opencollective":
            url = generate_opencollective_url(identifier, agg.total_amount)
            links.append(DonationLink(
                project_name=names,
                platform="Open Collective",
                url=url,
                amount=agg.total_amount,
                is_prefilled=True,
            ))
        elif platform == "github_sponsors":
            url = generate_github_sponsors_url(identifier)
            links.append(DonationLink(
                project_name=names,
                platform="GitHub Sponsors",
                url=url,
                amount=agg.total_amount,
                is_prefilled=False,
            ))
        else:
            links.append(DonationLink(
                project_name=names,
                platform="Direct",
                url=donation_url.url,
                amount=agg.total_amount,
                is_prefilled=False,
            ))

    return links


def generate_markdown_report(
    distribution: DistributionResult,
    title: str = "Donation Recommendations",
) -> str:
    """
    Generate a markdown report with donation links.

    Args:
        distribution: Distribution result from calculator
        title: Report title

    Returns:
        Markdown formatted report
    """
    lines = [
        f"# {title}",
        "",
        f"**Total: ${distribution.total_amount}**",
        "",
        "| Project | Amount | Platform | Link |",
        "|---------|--------|----------|------|",
    ]

    links = generate_donation_links(distribution)

    for link in links:
        prefill_note = " (pre-filled)" if link.is_prefilled else ""
        lines.append(
            f"| {link.project_name} | ${link.amount} | {link.platform}{prefill_note} | [Donate]({link.url}) |"
        )

    lines.extend([
        "",
        "---",
        "",
        "*Generated by [fundcli](https://github.com/your-repo/fundcli)*",
    ])

    return "\n".join(lines)


def generate_html_report(
    distribution: DistributionResult,
    title: str = "Donation Recommendations",
) -> str:
    """
    Generate an HTML report with clickable donation links.

    Args:
        distribution: Distribution result from calculator
        title: Report title

    Returns:
        HTML formatted report
    """
    links = generate_donation_links(distribution)

    rows = []
    for link in links:
        prefill = " ✓" if link.is_prefilled else ""
        rows.append(f"""
        <tr>
            <td>{link.project_name}</td>
            <td>${link.amount}</td>
            <td>{link.platform}{prefill}</td>
            <td><a href="{link.url}" target="_blank">Donate</a></td>
        </tr>""")

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }}
        h1 {{ color: #333; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; }}
        a {{ color: #0066cc; }}
        .total {{ font-size: 1.25rem; font-weight: bold; margin: 1rem 0; }}
        .note {{ color: #666; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p class="total">Total: ${distribution.total_amount}</p>
    <table>
        <thead>
            <tr>
                <th>Project</th>
                <th>Amount</th>
                <th>Platform</th>
                <th>Action</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    <p class="note">✓ = amount pre-filled in donation form</p>
    <hr>
    <p class="note">Generated by <a href="https://github.com/your-repo/fundcli">fundcli</a></p>
</body>
</html>"""
