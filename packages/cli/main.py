"""CLI entrypoint for Rhumb."""

import typer

from commands import (
    bench,
    chart,
    compare,
    evaluate,
    failures,
    find,
    leaderboard,
    score,
    tester_fleet,
    watch,
)

app = typer.Typer(help="Rhumb: Agent-native tool discovery and scoring")

app.command()(find.find)
app.command()(score.score)
app.command()(chart.chart)
app.command()(compare.compare)
app.command()(leaderboard.leaderboard)
app.command()(failures.failures)
app.command()(bench.bench)
app.command()(watch.watch)
app.command()(evaluate.evaluate)
app.command()(tester_fleet.test_battery)

if __name__ == "__main__":
    app()
