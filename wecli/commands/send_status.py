"""Inspect or reconcile a durable attempt without submitting again."""

import json

import click

from ..core.operations import operation_path, save_operation, send_lock
from ..core.sending import LocalReceipt
from ..output.formatter import output


@click.command("send-status")
@click.argument("operation_id")
@click.option("--reconcile", is_flag=True, help="Look for a new matching outgoing local record")
@click.pass_context
def send_status(ctx, operation_id, reconcile):
    """Inspect a send attempt; reconciliation never retries a send."""
    app = ctx.obj
    with send_lock():
        with open(operation_path(app, operation_id), encoding="utf-8") as handle:
            result = json.load(handle)
        if reconcile and result["status"] == "unknown":
            receipt = LocalReceipt(app, result["recipient"], result["message"])
            if receipt.self_username != result["self_username"]:
                raise click.ClickException("Account changed; reconciliation stopped")
            receipt.cutoff = result["cutoff"]
            receipt.baseline = {tuple(k): None for k in result["baseline"]}
            record = receipt.wait(0)
            if record:
                result.update(status="recorded", local_record_confirmed=True, local_record=record)
                save_operation(app, result)
        output(result, "json")
