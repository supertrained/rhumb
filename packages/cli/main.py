"""CLI entrypoint for Rhumb."""

import typer

from commands import (
    find,
    score,
    tester_fleet,
)

app = typer.Typer(help="Rhumb: Agent-native tool discovery and scoring")

app.command()(find.find)
app.command()(score.score)
app.command()(tester_fleet.test_battery)

if __name__ == "__main__":
    app()
