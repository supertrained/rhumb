"""`rhumb watch` command."""

import typer


def watch(service: str) -> None:
    """Watch a service for alerts."""
    typer.echo(f"watch scaffold: service={service}")
