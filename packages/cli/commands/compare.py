"""`rhumb compare` command."""

import typer


def compare(a: str, b: str) -> None:
    """Compare two services."""
    typer.echo(f"compare scaffold: a={a}, b={b}")
