"""`rhumb bench` command."""

import typer


def bench(service: str) -> None:
    """Run benchmark probe scaffolding command."""
    typer.echo(f"bench scaffold: service={service}")
