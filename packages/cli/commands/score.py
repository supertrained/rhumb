"""`rhumb score` command."""

import typer


def score(service: str, dimensions: bool = False) -> None:
    """Show AN score for a service."""
    typer.echo(f"score scaffold: service={service}, dimensions={dimensions}")
