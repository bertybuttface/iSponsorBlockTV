import logging
import os
import rich_click as click
import webbrowser
from appdirs import user_data_dir
from iSponsorBlockTV.utils.config import Config
from iSponsorBlockTV.core.devices import DeviceManager
from iSponsorBlockTV.utils.web import SetupServer

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
    config = Config.load(ctx.obj["data_dir"])
    config.validate_config()
    manager = DeviceManager(config, ctx.obj["debug"])
    manager.run()

@cli.group(invoke_without_command=True)
@click.pass_context
def config(ctx):
    """Configure iSponsorBlockTV"""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

@config.command(name="web")
@click.option('--port', '-p', default=8080, help='Port to run the web interface on')
@click.option('--no-browser', is_flag=True, help='Don\'t open browser automatically')
@click.pass_context
def config_web(ctx, port, no_browser):
    """Configure through web interface"""
    try:
        server = SetupServer(ctx.obj["data_dir"])
        
        if not no_browser:
            webbrowser.open(f'http://localhost:{port}')
            click.echo("Opening configuration page in your browser...")
        
        click.echo(f"Configuration server running at http://localhost:{port}")
        click.echo("Press Ctrl+C to stop")
        
        server.run(host='localhost', port=port)
    except KeyboardInterrupt:
        click.echo("\nShutting down configuration server...")
    except Exception as e:
        click.echo(f"Error starting configuration server: {e}", err=True)
        ctx.exit(1)

# You can add more config subcommands here, like:
@config.command(name="list")
@click.pass_context
def config_list(ctx):
    """List current configuration"""
    config = Config.load(ctx.obj["data_dir"])
    click.echo(f"Data directory: {ctx.obj['data_dir']}")
    click.echo(f"Devices: {len(config.devices)}")
    click.echo(f"Skip categories: {', '.join(config.skip_categories)}")
    click.echo(f"Report skipped segments: {config.skip_count_tracking}")
    click.echo(f"Mute ads: {config.mute_ads}")
    click.echo(f"Skip ads: {config.skip_ads}")
    click.echo(f"Autoplay: {config.auto_play}")

@config.command(name="validate")
@click.pass_context
def config_validate(ctx):
    """List current configuration"""
    config = Config.load(ctx.obj["data_dir"])
    config.validate_config()
    click.echo("Config valid if no errors shown.")

def app_start():
    """Entry point for the CLI application"""
    cli(obj={})
