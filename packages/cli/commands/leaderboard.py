"""`rhumb leaderboard` command."""

import typer


def leaderboard(category: str) -> None:
    """Show leaderboard for category."""
    typer.echo(f"leaderboard scaffold: category={category}")
