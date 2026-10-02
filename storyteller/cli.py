"""Typer CLI interface for StoryBI."""

from pathlib import Path
import typer
from rich.console import Console
from storyteller import __version__
from storyteller.exceptions import StoryBIError, UserConfirmationRequired

app = typer.Typer(
    name="storyteller",
    help="StoryBI: Autonomous LLM-Powered Storytelling Agent for Power BI.",
    add_completion=False,
)
console = Console()


def handle_cli_error(e: Exception) -> None:
    """Format and print StoryBI exceptions cleanly without tracebacks."""
    if isinstance(e, UserConfirmationRequired):
        console.print(f"[bold yellow]Confirmation required ({e.issue_type}):[/bold yellow] {e.message}")
        if e.options:
            console.print("[yellow]Options:[/yellow]")
            for opt in e.options:
                console.print(f"  * {opt}")
        if e.default_assumption is not None:
            console.print(f"Default assumption: [bold]{e.default_assumption}[/bold] (run with --yes to accept automatically)")
        raise typer.Exit(code=1)
    elif isinstance(e, StoryBIError):
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)
    raise e


@app.command()
def version():
    """Display StoryBI version."""
    console.print(f"[bold cyan]StoryBI[/bold cyan] version [bold green]{__version__}[/bold green]")


@app.command()
def run(
    file_path: str = typer.Argument(..., help="Path to input dataset (CSV, XLSX, Parquet, JSON, SQLite)"),
    output_dir: str = typer.Option("output", "--output", "-o", help="Target output directory for .pbip project"),
    theme: str = typer.Option("light_executive_slate", "--theme", "-t", help="Theme: light_executive_slate or dark_midnight_obsidian"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept all default assumptions without interactive prompts"),
):
    """Run full end-to-end pipeline: Ingest -> Profile -> Clean -> Facts -> Story -> PBIP."""
    try:
        console.print(f"[bold blue]Starting StoryBI end-to-end pipeline for:[/bold blue] {file_path}")
        console.print(f"Target output: [bold]{output_dir}[/bold] | Theme: [bold]{theme}[/bold] | Non-interactive: [bold]{yes}[/bold]")
        # Pipeline stages will be invoked here as they are implemented in subsequent phases.
    except (UserConfirmationRequired, StoryBIError) as e:
        handle_cli_error(e)


@app.command()
def ingest(
    file_path: str = typer.Argument(..., help="Path to input dataset"),
    output: str = typer.Option("ingest_report.json", "--output", "-o", help="Output path for report JSON"),
):
    """Ingest a dataset and output ingest_report.json."""
    try:
        from storyteller.ingest import ingest_file
        console.print(f"[bold cyan]Ingesting:[/bold cyan] {file_path}")
        frames, report = ingest_file(file_path)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
        console.print(f"[bold green]Ingest complete![/bold green] Format: {report.file_format}, Tables: {len(report.tables)}")
        console.print(f"Report saved to [bold]{output}[/bold]")
    except (UserConfirmationRequired, StoryBIError) as e:
        handle_cli_error(e)


@app.command()
def profile(
    file_path: str = typer.Argument(..., help="Path to input dataset"),
    output: str = typer.Option("profile.json", "--output", "-o", help="Output path for profile JSON"),
):
    """Profile columns, semantic roles, and data quality issues."""
    try:
        from storyteller.ingest import ingest_file
        from storyteller.profiler import profile_dataframe
        console.print(f"[bold cyan]Profiling:[/bold cyan] {file_path}")
        frames, _ = ingest_file(file_path)
        # Profile main table
        main_key = "main" if "main" in frames else list(frames.keys())[0]
        data_profile = profile_dataframe(frames[main_key], table_name=main_key)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(data_profile.model_dump_json(indent=2))
        console.print(f"[bold green]Profile complete![/bold green] Rows: {data_profile.total_rows}, Columns: {data_profile.total_columns}")
        console.print(f"North Star Metric: [bold magenta]{data_profile.suggested_north_star}[/bold magenta]")
        console.print(f"Primary Date: [bold yellow]{data_profile.primary_date_column}[/bold yellow]")
        console.print(f"Profile saved to [bold]{output}[/bold]")
    except (UserConfirmationRequired, StoryBIError) as e:
        handle_cli_error(e)


@app.command()
def clean(
    file_path: str = typer.Argument(..., help="Path to input dataset"),
    output: str = typer.Option("clean_data.csv", "--output", "-o", help="Path for cleaned output"),
    log_output: str = typer.Option("cleaning_log.json", "--log", "-l", help="Path for cleaning log JSON"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept default cleaning assumptions"),
):
    """Clean dataset, perform reconciliation checks, and emit cleaning_log.json."""
    try:
        from storyteller.ingest import ingest_file
        from storyteller.profiler import profile_dataframe
        from storyteller.cleaner import clean_dataframe
        console.print(f"[bold cyan]Cleaning:[/bold cyan] {file_path} (yes={yes})")
        frames, _ = ingest_file(file_path)
        main_key = "main" if "main" in frames else list(frames.keys())[0]
        df = frames[main_key]
        prof = profile_dataframe(df, table_name=main_key)

        clean_df, log = clean_dataframe(df, prof, yes=yes)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(log_output).parent.mkdir(parents=True, exist_ok=True)
        clean_df.to_csv(output, index=False)
        with open(log_output, "w", encoding="utf-8") as f:
            f.write(log.model_dump_json(indent=2))

        console.print(f"[bold green]Cleaning complete![/bold green] Clean data: {output}, Log: {log_output}")
        console.print(f"Reconciliation: [bold]{'PASSED' if log.reconciliation.passed else 'FAILED'}[/bold]")
        if log.assumptions:
            console.print("[yellow]Assumptions logged under --yes:[/yellow]")
            for a in log.assumptions:
                console.print(f"  * {a}")
    except (UserConfirmationRequired, StoryBIError) as e:
        handle_cli_error(e)


@app.command()
def analyze(
    file_path: str = typer.Argument(..., help="Path to clean dataset"),
):
    """Execute Facts Engine and output facts.json with DuckDB dual-recompute."""
    console.print(f"[cyan]Analyzing facts:[/cyan] {file_path}")


@app.command("build-pbip")
def build_pbip(
    file_path: str = typer.Argument(..., help="Path to clean dataset"),
    output: str = typer.Option("Report.pbip", "--output", "-o", help="Target .pbip output path"),
    theme: str = typer.Option("light_executive_slate", "--theme", "-t", help="Theme palette"),
):
    """Render .pbip project from template, semantic model, and report spec."""
    console.print(f"[cyan]Building Power BI Project (.pbip):[/cyan] {output}")


@app.command()
def studio(
    port: int = typer.Option(8000, "--port", "-p", help="Port for local studio server"),
):
    """Launch local Web Studio & preview interface (Optional Phase 7)."""
    console.print(f"[cyan]Launching StoryBI Studio on port {port}...[/cyan]")


if __name__ == "__main__":
    app()
