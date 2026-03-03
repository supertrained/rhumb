"""`rhumb find` command."""

import typer


def find(query: str) -> None:
    """Search services by free-text query."""
    typer.echo(f"find scaffold: query={query}")
