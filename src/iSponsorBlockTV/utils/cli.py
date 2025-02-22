# utils/cli.py
import logging
import os

import rich_click as click
from appdirs import user_data_dir

from iSponsorBlockTV.utils.config import Config
from iSponsorBlockTV.core.devices import DeviceManager

@click.group(invoke_without_command=True)
@click.option(
    "--data",
    "-d",
    default=lambda: os.getenv("iSPBTV_data_dir") 
    or user_data_dir("iSponsorBlockTV", "dmunozv04"),
    help="data directory",
)
@click.option("--debug", is_flag=True, help="debug mode")
@click.pass_context
def cli(ctx, data, debug):
    """iSponsorblockTV"""
    ctx.ensure_object(dict)
    ctx.obj["data_dir"] = data
    ctx.obj["debug"] = debug
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    if ctx.invoked_subcommand is None:
        ctx.invoke(start)

@cli.command()
@click.pass_context
def start(ctx):
    """Start the main program"""
    config = Config(ctx.obj["data_dir"])
    config.validate()
    manager = DeviceManager(config, ctx.obj["debug"])
    manager.run()

def app_start():
    """Entry point for the CLI application"""
    cli(obj={})
