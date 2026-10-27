"""Read individual messages using a caller-owned durable cursor."""

import click

from ..core.stream import message_page
from ..output.formatter import output


@click.command("new-messages")
@click.option("--cursor", help="Previous next_cursor; omit to read from the beginning")
@click.option("--limit", default=100, type=click.IntRange(1, 10000))
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]))
@click.pass_context
def new_messages(ctx, cursor, limit, fmt):
    """Read message rows. Save next_cursor only AFTER successfully processing the page."""
    result = message_page(ctx.obj, cursor, limit)
    output(result, fmt)
