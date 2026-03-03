"""`rhumb evaluate` command."""

import typer


def evaluate(stack: str = typer.Option(..., help="Comma-separated service list")) -> None:
    """Evaluate an entire service stack."""
    typer.echo(f"evaluate scaffold: stack={stack}")
