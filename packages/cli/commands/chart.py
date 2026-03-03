"""`rhumb chart` command."""

import typer


def chart(service: str) -> None:
    """Show a service profile chart."""
    typer.echo(f"chart scaffold: service={service}")
