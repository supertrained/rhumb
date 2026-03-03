"""`rhumb failures` command."""

import typer


def failures(service: str) -> None:
    """Show failures for a service."""
    typer.echo(f"failures scaffold: service={service}")
