"""Command-line interface for fundcli."""

from decimal import Decimal
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from fundcli import __version__
from fundcli.analyzer import analyze_usage, get_top_executables, get_top_projects
from fundcli.calculator import calculate_distribution, WeightingStrategy
from fundcli.config import load_config, get_default_config_content, get_config_path
from fundcli.database import TimePeriod, get_history_stats
from fundcli.mapper import create_mapper

app = typer.Typer(
    name="fundcli",
    help="Analyze Atuin command history and recommend donations to open source projects.",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"fundcli version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
):
    """Analyze Atuin command history and recommend donations to open source projects."""
    pass


@app.command()
def analyze(
    period: str = typer.Option(
        "month",
        "--period", "-p",
        help="Time period: day, week, month, year, all",
    ),
    hostname: str = typer.Option(
        None,
        "--hostname", "-H",
        help="Filter by hostname",
    ),
    limit: int = typer.Option(
        20,
        "--limit", "-l",
        help="Number of top executables to show",
    ),
    show_unknown: bool = typer.Option(
        True,
        "--unknown/--no-unknown",
        help="Show unknown executables",
    ),
):
    """Analyze command usage patterns."""
    config = load_config()

    try:
        time_period = TimePeriod(period)
    except ValueError:
        console.print(f"[red]Invalid period: {period}[/red]")
        console.print("Valid periods: day, week, month, year, all")
        raise typer.Exit(1)

    mapper = create_mapper()

    # Apply custom mappings from config
    for exe, project_id in config.custom_mappings.items():
        mapper.add_custom_mapping(exe, project_id)

    with console.status("Analyzing command history..."):
        analysis = analyze_usage(
            mapper=mapper,
            period=time_period,
            hostname=hostname,
            include_builtins=config.analysis.include_builtins,
            db_path=config.database.path if config.database.path.exists() else None,
        )

    # Header
    period_str = f"{analysis.period_start:%Y-%m-%d}" if analysis.period_start else "beginning"
    console.print(Panel(
        f"[bold]Command Usage Analysis[/bold]\n"
        f"Period: {period_str} to {analysis.period_end:%Y-%m-%d}\n"
        f"Total commands: {analysis.total_commands:,}\n"
        f"Unique executables: {analysis.total_executables}",
        title="fundcli",
        box=box.ROUNDED,
    ))

    # Top executables table
    console.print("\n[bold]Top Executables[/bold]")
    table = Table(box=box.SIMPLE)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Executable", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("%", justify="right")
    table.add_column("Project", style="green")

    top_exes = get_top_executables(analysis, limit)
    total_exe_count = sum(s.count for _, s in top_exes)

    for i, (exe, stats) in enumerate(top_exes, 1):
        pct = (stats.count / analysis.total_commands * 100) if analysis.total_commands > 0 else 0
        project = mapper.get_project_for_executable(exe)
        project_name = project.name if project else "[dim]unknown[/dim]"

        table.add_row(
            str(i),
            exe,
            f"{stats.count:,}",
            f"{pct:.1f}%",
            project_name,
        )

    console.print(table)

    # Unknown executables
    if show_unknown and analysis.unknown_executables:
        console.print(f"\n[bold yellow]Unknown Executables[/bold yellow] ({len(analysis.unknown_executables)} total)")

        # Show top 10 unknown by count
        sorted_unknown = sorted(
            analysis.unknown_executables.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        unknown_table = Table(box=box.SIMPLE)
        unknown_table.add_column("Executable", style="yellow")
        unknown_table.add_column("Count", justify="right")

        for exe, count in sorted_unknown:
            unknown_table.add_row(exe, str(count))

        console.print(unknown_table)
        console.print("\n[dim]Run 'fundcli unknowns' to investigate and classify these executables.[/dim]")


@app.command()
def recommend(
    amount: float = typer.Option(
        ...,
        "--amount", "-a",
        help="Total donation amount in USD",
    ),
    period: str = typer.Option(
        "month",
        "--period", "-p",
        help="Time period: day, week, month, year, all",
    ),
    max_projects: int = typer.Option(
        10,
        "--max-projects", "-n",
        help="Maximum number of projects",
    ),
    min_amount: float = typer.Option(
        1.0,
        "--min-amount", "-m",
        help="Minimum donation per project",
    ),
    weight: str = typer.Option(
        "count",
        "--weight", "-w",
        help="Weighting strategy: count, duration, success, combined",
    ),
    format: str = typer.Option(
        "table",
        "--format", "-f",
        help="Output format: table, markdown, json",
    ),
    hostname: str = typer.Option(
        None,
        "--hostname", "-H",
        help="Filter by hostname",
    ),
):
    """Generate donation recommendations based on usage."""
    config = load_config()

    try:
        time_period = TimePeriod(period)
    except ValueError:
        console.print(f"[red]Invalid period: {period}[/red]")
        raise typer.Exit(1)

    try:
        strategy = WeightingStrategy(weight)
    except ValueError:
        console.print(f"[red]Invalid weighting strategy: {weight}[/red]")
        console.print("Valid strategies: count, duration, success, combined")
        raise typer.Exit(1)

    mapper = create_mapper()

    # Apply custom mappings
    for exe, project_id in config.custom_mappings.items():
        mapper.add_custom_mapping(exe, project_id)

    with console.status("Analyzing command history..."):
        analysis = analyze_usage(
            mapper=mapper,
            period=time_period,
            hostname=hostname,
            include_builtins=config.analysis.include_builtins,
            db_path=config.database.path if config.database.path.exists() else None,
        )

    if not analysis.project_stats:
        console.print("[yellow]No known projects found in command history.[/yellow]")
        raise typer.Exit(0)

    distribution = calculate_distribution(
        analysis=analysis,
        total_amount=Decimal(str(amount)),
        strategy=strategy,
        min_amount=Decimal(str(min_amount)),
        max_projects=max_projects,
    )

    # Output based on format
    if format == "json":
        import json
        output = {
            "total_amount": str(distribution.total_amount),
            "period": period,
            "weighting": weight,
            "recommendations": [
                {
                    "project": rec.project.name,
                    "project_id": rec.project.id,
                    "amount": str(rec.amount),
                    "percentage": rec.percentage,
                    "usage_count": rec.usage_count,
                    "donation_url": rec.project.primary_donation_url,
                }
                for rec in distribution.recommendations
            ],
        }
        console.print(json.dumps(output, indent=2))

    elif format == "markdown":
        period_str = f"{analysis.period_start:%Y-%m-%d}" if analysis.period_start else "beginning"
        console.print(f"# Donation Recommendations (${amount:.2f})")
        console.print(f"\nBased on usage from {period_str} to {analysis.period_end:%Y-%m-%d}")
        console.print(f"({analysis.total_commands:,} commands analyzed)\n")
        console.print("| Project | Amount | Usage | Donate At |")
        console.print("|---------|--------|-------|-----------|")
        for rec in distribution.recommendations:
            url = rec.project.primary_donation_url or "N/A"
            capped = "*" if rec.capped_at_minimum else ""
            console.print(f"| {rec.project.name} | ${rec.amount}{capped} | {rec.percentage:.1f}% | {url} |")
        if any(r.capped_at_minimum for r in distribution.recommendations):
            console.print(f"\n*Minimum threshold (${min_amount:.2f}) applied")

    else:  # table
        period_str = f"{analysis.period_start:%Y-%m-%d}" if analysis.period_start else "beginning"
        console.print(Panel(
            f"[bold]Donation Recommendations[/bold] (${amount:.2f} total)\n"
            f"Period: {period_str} to {analysis.period_end:%Y-%m-%d}\n"
            f"Commands analyzed: {analysis.total_commands:,}\n"
            f"Weighting: {weight}",
            title="fundcli recommend",
            box=box.ROUNDED,
        ))

        table = Table(box=box.SIMPLE)
        table.add_column("Project", style="cyan")
        table.add_column("Amount", justify="right", style="green")
        table.add_column("Usage", justify="right")
        table.add_column("Donate At", style="blue")

        for rec in distribution.recommendations:
            url = rec.project.primary_donation_url or "[dim]no link[/dim]"
            amount_str = f"${rec.amount}"
            if rec.capped_at_minimum:
                amount_str += "*"

            table.add_row(
                rec.project.name,
                amount_str,
                f"{rec.percentage:.1f}%",
                url,
            )

        console.print(table)

        if any(r.capped_at_minimum for r in distribution.recommendations):
            console.print(f"\n[dim]* Minimum threshold (${min_amount:.2f}) applied[/dim]")

        console.print(f"\n[bold]Total: ${distribution.allocated_amount}[/bold]")

        # Show unknown executables hint
        if analysis.unknown_executables:
            console.print(f"\n[dim]{len(analysis.unknown_executables)} unknown executables not included.[/dim]")
            console.print("[dim]Run 'fundcli analyze' to see them.[/dim]")


@app.command()
def projects(
    search: str = typer.Argument(
        None,
        help="Search query (name, executable, or description)",
    ),
    list_all: bool = typer.Option(
        False,
        "--all", "-a",
        help="List all projects",
    ),
):
    """Search or list known projects."""
    mapper = create_mapper()

    if search:
        results = mapper.search_projects(search)
        if not results:
            console.print(f"[yellow]No projects found matching '{search}'[/yellow]")
            raise typer.Exit(0)

        for project in results:
            console.print(f"\n[bold cyan]{project.name}[/bold cyan] ({project.id})")
            if project.description:
                console.print(f"  {project.description}")
            console.print(f"  [dim]Executables:[/dim] {', '.join(project.executables)}")
            if project.donation_urls:
                console.print(f"  [dim]Donate:[/dim] {project.primary_donation_url}")

    elif list_all:
        all_projects = mapper.all_projects()
        table = Table(title=f"Known Projects ({len(all_projects)} total)", box=box.SIMPLE)
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Executables", style="dim")

        for project in sorted(all_projects, key=lambda p: p.id):
            exes = ", ".join(project.executables[:3])
            if len(project.executables) > 3:
                exes += f" (+{len(project.executables) - 3})"
            table.add_row(project.id, project.name, exes)

        console.print(table)

    else:
        console.print("Usage: fundcli projects [SEARCH] or fundcli projects --all")
        console.print("\nExamples:")
        console.print("  fundcli projects curl     # Search for 'curl'")
        console.print("  fundcli projects python   # Search for 'python'")
        console.print("  fundcli projects --all    # List all projects")


@app.command()
def config(
    show: bool = typer.Option(
        False,
        "--show", "-s",
        help="Show current configuration",
    ),
    init: bool = typer.Option(
        False,
        "--init",
        help="Create default configuration file",
    ),
    path: bool = typer.Option(
        False,
        "--path",
        help="Show configuration file path",
    ),
):
    """View or initialize configuration."""
    config_path = get_config_path()

    if path:
        console.print(str(config_path))
        return

    if init:
        if config_path.exists():
            console.print(f"[yellow]Config file already exists at {config_path}[/yellow]")
            raise typer.Exit(1)

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(get_default_config_content())
        console.print(f"[green]Created config file at {config_path}[/green]")
        return

    if show or not (init or path):
        if not config_path.exists():
            console.print(f"[dim]No config file found at {config_path}[/dim]")
            console.print("Run 'fundcli config --init' to create one.")
            return

        console.print(f"[dim]Config file: {config_path}[/dim]\n")
        console.print(config_path.read_text())


@app.command()
def stats():
    """Show database statistics."""
    config = load_config()
    db_path = config.database.path

    if not db_path.exists():
        console.print(f"[red]Database not found at {db_path}[/red]")
        raise typer.Exit(1)

    stats = get_history_stats(db_path)

    oldest_str = stats['oldest'].strftime('%Y-%m-%d %H:%M:%S') if stats['oldest'] else 'N/A'
    newest_str = stats['newest'].strftime('%Y-%m-%d %H:%M:%S') if stats['newest'] else 'N/A'

    console.print(Panel(
        f"[bold]Atuin Database Statistics[/bold]\n\n"
        f"Path: {db_path}\n"
        f"Total commands: {stats['total_commands']:,}\n"
        f"Oldest: {oldest_str}\n"
        f"Newest: {newest_str}",
        box=box.ROUNDED,
    ))


@app.command()
def donate(
    amount: float = typer.Option(
        ...,
        "--amount", "-a",
        help="Total donation amount in USD",
    ),
    period: str = typer.Option(
        "month",
        "--period", "-p",
        help="Time period: day, week, month, year, all",
    ),
    max_projects: int = typer.Option(
        10,
        "--max-projects", "-n",
        help="Maximum number of projects",
    ),
    output_file: str = typer.Option(
        None,
        "--output", "-o",
        help="Output file for report (html or md extension)",
    ),
    open_links: bool = typer.Option(
        False,
        "--open",
        help="Open donation links in browser",
    ),
    hostname: str = typer.Option(
        None,
        "--hostname", "-H",
        help="Filter by hostname",
    ),
):
    """Generate donation links and reports."""
    from fundcli.integrations import (
        generate_donation_links,
        generate_markdown_report,
        generate_html_report,
    )
    import webbrowser

    config = load_config()

    try:
        time_period = TimePeriod(period)
    except ValueError:
        console.print(f"[red]Invalid period: {period}[/red]")
        raise typer.Exit(1)

    mapper = create_mapper()

    # Apply custom mappings
    for exe, project_id in config.custom_mappings.items():
        mapper.add_custom_mapping(exe, project_id)

    with console.status("Analyzing command history..."):
        analysis = analyze_usage(
            mapper=mapper,
            period=time_period,
            hostname=hostname,
            include_builtins=config.analysis.include_builtins,
            db_path=config.database.path if config.database.path.exists() else None,
        )

    if not analysis.project_stats:
        console.print("[yellow]No known projects found in command history.[/yellow]")
        raise typer.Exit(0)

    distribution = calculate_distribution(
        analysis=analysis,
        total_amount=Decimal(str(amount)),
        min_amount=Decimal(str(config.donation.min_per_project)),
        max_projects=max_projects,
    )

    # Generate links
    links = generate_donation_links(distribution)

    if not links:
        console.print("[yellow]No donation links available for recommended projects.[/yellow]")
        raise typer.Exit(0)

    # Output to file if requested
    if output_file:
        if output_file.endswith(".html"):
            content = generate_html_report(distribution)
        else:
            content = generate_markdown_report(distribution)

        Path(output_file).write_text(content)
        console.print(f"[green]Report saved to {output_file}[/green]")

    # Display links
    console.print(Panel(
        f"[bold]Donation Links[/bold] (${amount:.2f} total)\n"
        f"Click links to donate. ✓ = amount pre-filled",
        title="fundcli donate",
        box=box.ROUNDED,
    ))

    table = Table(box=box.SIMPLE)
    table.add_column("Project", style="cyan")
    table.add_column("Amount", justify="right", style="green")
    table.add_column("Platform")
    table.add_column("Link", style="blue")

    for link in links:
        prefill = " ✓" if link.is_prefilled else ""
        table.add_row(
            link.project_name,
            f"${link.amount}",
            f"{link.platform}{prefill}",
            link.url,
        )

    console.print(table)

    # Open links in browser if requested
    if open_links:
        console.print("\n[dim]Opening donation links in browser...[/dim]")
        for link in links:
            webbrowser.open(link.url)


# Unknowns subcommand group
unknowns_app = typer.Typer(
    name="unknowns",
    help="Investigate and classify unknown executables.",
)
app.add_typer(unknowns_app, name="unknowns")


@unknowns_app.callback(invoke_without_command=True)
def unknowns_list(
    ctx: typer.Context,
    refresh: bool = typer.Option(
        False,
        "--refresh", "-r",
        help="Re-investigate all unknowns (bypass cache)",
    ),
    period: str = typer.Option(
        "month",
        "--period", "-p",
        help="Time period for finding unknowns: day, week, month, year, all",
    ),
):
    """List and investigate unknown executables."""
    if ctx.invoked_subcommand is not None:
        return  # Subcommand will handle it

    from fundcli.local_db import LocalDatabase, get_db_path
    from fundcli.unknowns import investigate_and_save

    config = load_config()
    db = LocalDatabase()

    # Check if first run
    first_run = not db.db_exists() or len(db.list_unknowns()) == 0
    if first_run:
        console.print(f"[dim]Created local database at {get_db_path()}[/dim]\n")

    try:
        time_period = TimePeriod(period)
    except ValueError:
        console.print(f"[red]Invalid period: {period}[/red]")
        raise typer.Exit(1)

    mapper = create_mapper()

    # Get unknowns from analysis
    with console.status("Analyzing command history..."):
        analysis = analyze_usage(
            mapper=mapper,
            period=time_period,
            include_builtins=config.analysis.include_builtins,
            db_path=config.database.path if config.database.path.exists() else None,
        )

    if not analysis.unknown_executables:
        console.print("[green]No unknown executables found![/green]")
        raise typer.Exit(0)

    # Investigate each unknown
    unknowns_list = sorted(
        analysis.unknown_executables.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    console.print(Panel(
        f"[bold]Unknown Executables Investigation[/bold]\n"
        f"Found {len(unknowns_list)} unknowns in {period} history",
        title="fundcli unknowns",
        box=box.ROUNDED,
    ))

    if refresh or first_run:
        console.print("[dim]Investigating executables...[/dim]\n")

    table = Table(box=box.SIMPLE)
    table.add_column("Executable", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Type")
    table.add_column("Classification", style="yellow")
    table.add_column("Info")

    for exe, count in unknowns_list:
        # Skip if already classified as user/system/ignored
        cached = db.get_unknown(exe)
        if cached and cached.classification in ('user', 'system', 'ignored'):
            continue

        # Investigate (uses cache unless refresh)
        atuin_path = config.database.path if config.database.path.exists() else None
        with console.status(f"Investigating {exe}...") if (refresh or first_run) else nullcontext():
            unknown = investigate_and_save(exe, db, force=refresh, atuin_db_path=atuin_path)

        # Determine display info
        info = ""
        if unknown.copyright_found:
            info = unknown.copyright_found[:40] + "..." if len(unknown.copyright_found or "") > 40 else (unknown.copyright_found or "")
        elif unknown.path:
            # Show shortened path
            path = unknown.path
            home = str(Path.home())
            if path.startswith(home):
                path = "~" + path[len(home):]
            info = path[:40] + "..." if len(path) > 40 else path

        classification = unknown.classification or "unknown"
        type_str = unknown.file_type or "?"

        table.add_row(
            exe,
            str(count),
            type_str,
            classification,
            info,
        )

    console.print(table)

    console.print("\n[dim]Commands:[/dim]")
    console.print("  fundcli unknowns [NAME]              - Show details for an executable")
    console.print("  fundcli unknowns classify NAME TYPE  - Classify an executable")
    console.print("  fundcli unknowns reset               - Clear the local database")


# Need nullcontext for Python 3.11+
from contextlib import nullcontext


@unknowns_app.command("show")
def unknowns_show(
    name: str = typer.Argument(..., help="Executable name to investigate"),
):
    """Show detailed information about an unknown executable."""
    from fundcli.local_db import LocalDatabase
    from fundcli.unknowns import investigate_and_save

    config = load_config()
    db = LocalDatabase()
    atuin_path = config.database.path if config.database.path.exists() else None

    with console.status(f"Investigating {name}..."):
        unknown = investigate_and_save(name, db, force=True, atuin_db_path=atuin_path)

    console.print(Panel(
        f"[bold]{name}[/bold]",
        title="Executable Details",
        box=box.ROUNDED,
    ))

    console.print(f"[bold]Path:[/bold] {unknown.path or 'not found'}")
    console.print(f"[bold]Type:[/bold] {unknown.file_type or 'unknown'}")
    console.print(f"[bold]Classification:[/bold] {unknown.classification or 'unknown'}")

    if unknown.copyright_found:
        console.print(f"\n[bold]Copyright:[/bold]")
        console.print(f"  {unknown.copyright_found}")

    if unknown.help_text:
        console.print(f"\n[bold]Help Output:[/bold]")
        for line in unknown.help_text.split('\n')[:5]:
            console.print(f"  {line}")

    if unknown.suggested_project:
        console.print(f"\n[bold]Suggested Project:[/bold] {unknown.suggested_project}")

    if unknown.user_notes:
        console.print(f"\n[bold]Notes:[/bold] {unknown.user_notes}")


@unknowns_app.command("classify")
def unknowns_classify(
    name: str = typer.Argument(..., help="Executable name"),
    classification: str = typer.Argument(
        ...,
        help="Classification: user, system, third_party, ignored",
    ),
    project: str = typer.Option(
        None,
        "--project", "-p",
        help="Suggested project ID (for third_party)",
    ),
    notes: str = typer.Option(
        None,
        "--notes", "-n",
        help="User notes",
    ),
):
    """Classify an unknown executable."""
    from fundcli.local_db import LocalDatabase
    from fundcli.unknowns import classify_executable

    valid_classifications = ('user', 'system', 'third_party', 'ignored')
    if classification not in valid_classifications:
        console.print(f"[red]Invalid classification: {classification}[/red]")
        console.print(f"Valid options: {', '.join(valid_classifications)}")
        raise typer.Exit(1)

    config = load_config()
    db = LocalDatabase()
    atuin_path = config.database.path if config.database.path.exists() else None
    unknown = classify_executable(name, classification, db, project, notes, atuin_db_path=atuin_path)

    console.print(f"[green]✓[/green] Classified '{name}' as [yellow]{classification}[/yellow]")

    if classification in ('user', 'system', 'ignored'):
        console.print(f"  [dim]→ Will be excluded from donation calculations[/dim]")

    if classification == 'third_party' and not project:
        console.print(f"\n  [dim]Consider adding to projects.toml:[/dim]")
        console.print(f"    [{name}]")
        console.print(f'    name = "{name}"')
        console.print(f'    executables = ["{name}"]')
        console.print(f"    donation_urls = []")


@unknowns_app.command("reset")
def unknowns_reset(
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Skip confirmation",
    ),
):
    """Clear the local unknowns database."""
    from fundcli.local_db import LocalDatabase, get_db_path

    if not force:
        confirm = typer.confirm("This will clear all cached investigations. Continue?")
        if not confirm:
            raise typer.Abort()

    db = LocalDatabase()
    count = db.clear_all()
    console.print(f"[green]✓[/green] Cleared {count} records from {get_db_path()}")


if __name__ == "__main__":
    app()
