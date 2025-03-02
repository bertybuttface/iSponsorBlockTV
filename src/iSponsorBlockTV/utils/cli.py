import logging
import os

import rich_click as click
from appdirs import user_data_dir

from iSponsorBlockTV.core.devices import DeviceManager
from iSponsorBlockTV.utils.config import Config
from iSponsorBlockTV.utils.web import run_web_server


@click.group(invoke_without_command=True)
@click.option(
    "--data",
    "-d",
    default=lambda: os.getenv("iSPBTV_data_dir")
    or user_data_dir("iSponsorBlockTV", "dmunozv04"),
    help="Data directory path",
)
@click.option("--debug", is_flag=True, help="Enable debug mode with verbose logging")
@click.option(
    "--watch-config",
    is_flag=True,
    help="Watch config file for changes and reload automatically",
)
@click.option(
    "--web",
    "-w",
    is_flag=True,
    help="Run web configuration server alongside main application",
)
@click.option(
    "--port",
    "-p",
    default=8080,
    help="Port for web configuration server (only used with --web)",
)
@click.version_option()
@click.pass_context
def cli(ctx, data, debug, watch_config, web, port):
    """iSponsorBlockTV - Skip sponsor segments on your streaming devices"""
    ctx.ensure_object(dict)
    ctx.obj["data_dir"] = data
    ctx.obj["debug"] = debug
    # If web is enabled, automatically enable watch_config unless explicitly disabled
    # If web is disabled, automatically disable watch_config unless explicitly enabled.
    ctx.obj["watch_config"] = True if web else watch_config
    ctx.obj["web"] = web
    ctx.obj["port"] = port
    
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    
    if ctx.invoked_subcommand is None:
        ctx.invoke(start)


@cli.command()
@click.pass_context
def start(ctx):
    """Start the main program"""
    try:
        config = Config.load(ctx.obj["data_dir"])
        config.validate_config()
        
        # Start web server if requested
        web_process = None
        if ctx.obj["web"]:
            import multiprocessing
            
            # Always enable config watching with web server
            ctx.obj["watch_config"] = True
            
            web_process = multiprocessing.Process(
                target=run_web_server,
                args=(ctx.obj["data_dir"], ctx.obj["port"], True),  # True for headless mode
            )
            web_process.daemon = True
            web_process.start()
            click.echo(f"Web configuration running at http://localhost:{ctx.obj['port']}")
        
        # Start the main application
        click.echo("Starting iSponsorBlockTV...")
        manager = DeviceManager(
            config, ctx.obj["debug"], watch_config=ctx.obj["watch_config"]
        )
        manager.run()
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if ctx.obj["debug"]:
            import traceback
            traceback.print_exc()
        ctx.exit(1)
    finally:
        # Clean up web server process if running
        if 'web_process' in locals() and web_process and web_process.is_alive():
            web_process.terminate()
            web_process.join()


@cli.command(name="web")
@click.option("--port", "-p", default=8080, help="Port to run the web interface on")
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
@click.pass_context
def config_web(ctx, port, no_browser):
    """Run the web configuration interface only"""
    try:
        click.echo(f"Starting web configuration server on port {port}...")
        run_web_server(ctx.obj["data_dir"], port, no_browser)
    except KeyboardInterrupt:
        click.echo("\nShutting down configuration server...")
    except Exception as e:
        click.echo(f"Error starting configuration server: {e}", err=True)
        if ctx.obj["debug"]:
            import traceback
            traceback.print_exc()
        ctx.exit(1)


@cli.command(name="info")
@click.pass_context
def config_info(ctx):
    """Display current configuration"""
    try:
        config = Config.load(ctx.obj["data_dir"])
        click.echo(f"Data directory: {ctx.obj['data_dir']}")
        click.echo(f"Devices: {len(config.devices)}")
        for i, device in enumerate(config.devices, 1):
            click.echo(f"  {i}. {device.name} ({device.screen_id})")
        click.echo(f"Skip categories: {', '.join(config.skip_categories)}")
        click.echo(f"Report skipped segments: {config.skip_count_tracking}")
        click.echo(f"Mute ads: {config.mute_ads}")
        click.echo(f"Skip ads: {config.skip_ads}")
        click.echo(f"Autoplay: {config.auto_play}")
    except Exception as e:
        click.echo(f"Error reading configuration: {e}", err=True)
        if ctx.obj["debug"]:
            import traceback
            traceback.print_exc()
        ctx.exit(1)


def app_start():
    """Entry point for the CLI application"""
    cli(obj={})


if __name__ == "__main__":
    app_start()
