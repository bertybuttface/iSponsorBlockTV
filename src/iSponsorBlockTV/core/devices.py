import asyncio
import logging
import time
from signal import SIGINT, SIGTERM
from typing import Dict, List, Optional

import aiohttp

from iSponsorBlockTV.core.sponsorblock import ApiHelper
from iSponsorBlockTV.core.youtube import YtLoungeApi
from iSponsorBlockTV.utils.config import Config
from iSponsorBlockTV.utils.config_watcher import ConfigWatcher


class DeviceManager:
    def __init__(self, config, debug: bool = False, watch_config: bool = False):
        self.config = config
        self.debug = debug
        self.watch_config = watch_config
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.tasks: List[asyncio.Task] = []
        self.devices: Dict[str, "DeviceListener"] = {}  # Keyed by screen_id
        self.web_session: Optional[aiohttp.ClientSession] = None
        self.tcp_connector: Optional[aiohttp.TCPConnector] = None
        self.api_helper: Optional[ApiHelper] = None
        self.config_watcher = None

        # Set up logging
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)

    async def reload_config(self):
        """Reload configuration without stopping anything"""
        try:
            logging.info("Reloading configuration")
            logging.debug(f"Old config: {self.config.model_dump_json(indent=2)}")

            # Load the new configuration
            new_config = Config.load(self.config.config_file.parent)

            # Update API helper settings
            await self.update_api_helper(new_config)

            # Update device settings and handle additions/removals
            await self.update_devices(new_config)

            # Save the new config reference
            self.config = new_config

            logging.info("Configuration successfully reloaded")
            logging.debug(f"New config: {self.config.model_dump_json(indent=2)}")
        except Exception as e:
            logging.error(f"Error reloading configuration: {e}", exc_info=True)

    async def update_api_helper(self, new_config):
        """Update API helper with new configuration"""
        if self.api_helper:
            self.api_helper.apikey = new_config.apikey
            self.api_helper.skip_categories = new_config.skip_categories
            self.api_helper.skip_count_tracking = new_config.skip_count_tracking

    async def update_devices(self, new_config):
        """Update devices based on new configuration"""
        # Get current and new device IDs
        current_device_ids = set(self.devices.keys())
        new_device_ids = {device.screen_id for device in new_config.devices}

        # Handle removed devices
        for device_id in current_device_ids - new_device_ids:
            logging.info(f"Removing device {device_id}")
            device = self.devices.pop(device_id)
            await device.cancel()

        # Handle added and updated devices
        for device_config in new_config.devices:
            screen_id = device_config.screen_id

            if screen_id in self.devices:
                # Update existing device
                device = self.devices[screen_id]
                logging.info(f"Updating device {screen_id}")
                device.offset = device_config.offset
                device.name = device_config.name

                # Update lounge controller settings
                if device.lounge_controller:
                    device.lounge_controller.mute_ads = new_config.mute_ads
                    device.lounge_controller.skip_ads = new_config.skip_ads
                    device.lounge_controller.auto_play = new_config.auto_play
            else:
                # Add new device
                logging.info(f"Adding new device {screen_id}")
                await self.add_device(device_config)

    async def add_device(self, device_config):
        """Add a new device and start its tasks"""
        try:
            from iSponsorBlockTV.core.devices import DeviceListener

            device = DeviceListener(
                self.api_helper,
                self.config,
                device_config,
                self.debug,
                self.web_session,
            )
            await device.initialize_web_session()

            # Add device to our managed devices
            self.devices[device_config.screen_id] = device

            # Create and track device tasks
            device_tasks = [
                self.loop.create_task(device.loop()),
                self.loop.create_task(device.refresh_auth_loop()),
            ]

            # Store tasks for cleanup
            self.tasks.extend(device_tasks)

            logging.info(f"Successfully added device: {device_config.name}")
        except Exception as e:
            logging.error(
                f"Failed to add device {device_config.screen_id}: {e}", exc_info=True
            )

    async def initialize(self):
        """Initialize network resources and create device listeners"""
        self.loop = asyncio.get_event_loop()
        if self.debug:
            self.loop.set_debug(True)

        # Set up network resources
        self.tcp_connector = aiohttp.TCPConnector(ttl_dns_cache=300)
        self.web_session = aiohttp.ClientSession(connector=self.tcp_connector)
        self.api_helper = ApiHelper(self.config, self.web_session)

        # Initialize devices
        for device_config in self.config.devices:
            await self.add_device(device_config)

        # Set up config watcher if enabled
        if self.watch_config:
            self.config_watcher = ConfigWatcher(
                self.config.config_file, self.reload_config
            )
            # Set the event loop reference
            self.config_watcher.set_loop(self.loop)
            self.config_watcher.start()

    async def cleanup(self):
        """Clean up all resources"""
        # Cancel all devices
        for device in list(self.devices.values()):
            try:
                # Create tasks for each device's cancel coroutine
                self.loop.create_task(device.cancel())
            except Exception as e:
                logging.error(f"Error cancelling device: {e}", exc_info=True)

        # Give a moment for devices to start canceling
        await asyncio.sleep(0.5)

        # Cancel all pending tasks
        for task in self.tasks:
            if not task.done() and not task.cancelled():
                try:
                    task.cancel()
                except Exception:
                    pass

        # Wait for all tasks to complete cancellation with timeout
        if self.tasks:
            try:
                # Use asyncio.wait on the task list
                done, pending = await asyncio.wait(
                    self.tasks, timeout=5, return_when=asyncio.ALL_COMPLETED
                )

                # Log any tasks that didn't complete
                if pending:
                    logging.warning(
                        f"{len(pending)} tasks did not complete during cleanup"
                    )
            except Exception as e:
                logging.error(
                    f"Error waiting for tasks to complete: {e}", exc_info=True
                )

        # Close network resources
        if self.web_session:
            await self.web_session.close()
        if self.tcp_connector:
            await self.tcp_connector.close()

        # Stop config watcher - only at final shutdown
        if self.config_watcher:
            self.config_watcher.stop()

    async def handle_signal(self, termination_future):
        """Handle system signals"""
        if not termination_future.done():
            termination_future.set_result(None)
        logging.info("Received termination signal, shutting down...")

    async def run_async(self):
        """Main async execution loop"""
        try:
            await self.initialize()

            # Create a future to wait for termination signals
            termination_future = asyncio.Future()

            # Set up signal handlers
            for sig in (SIGTERM, SIGINT):
                self.loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(self.handle_signal(termination_future)),
                )

            # Wait for termination signal
            await termination_future

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received, shutting down...")
        except Exception as e:
            logging.error(f"Unhandled exception in main loop: {e}", exc_info=True)
        finally:
            # Clean up resources
            logging.info("Performing cleanup...")
            await self.cleanup()
            logging.info("Exited cleanly")

    def run(self):
        """Main entry point"""
        self.loop = asyncio.get_event_loop()
        try:
            self.loop.run_until_complete(self.run_async())
        except Exception as e:
            logging.error(f"Fatal error: {e}", exc_info=True)
        finally:
            if not self.loop.is_closed():
                self.loop.close()


class DeviceListener:
    def __init__(self, api_helper, config, device, debug: bool, web_session):
        self.task: Optional[asyncio.Task] = None
        self.api_helper: ApiHelper = api_helper
        self.offset = device.offset
        self.name = device.name
        self.cancelled = False
        self.logger = logging.getLogger(f"iSponsorBlockTV-{device.screen_id}")
        self.web_session = web_session
        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        sh = logging.StreamHandler()
        sh.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        self.logger.addHandler(sh)
        self.logger.info("Starting device")
        self.lounge_controller = YtLoungeApi(
            device.screen_id, config, api_helper, self.logger
        )

    # Ensures that we have a valid auth token
    async def refresh_auth_loop(self):
        while True:
            await asyncio.sleep(60 * 60 * 24)  # Refresh every 24 hours
            try:
                await self.lounge_controller.refresh_auth()
            except BaseException:
                # traceback.print_exc()
                pass

    async def is_available(self):
        try:
            return await self.lounge_controller.is_available()
        except BaseException:
            # traceback.print_exc()
            return False

    # Main subscription loop
    async def loop(self):
        lounge_controller = self.lounge_controller
        while not self.cancelled:
            while not lounge_controller.linked():
                try:
                    self.logger.debug("Refreshing auth")
                    await lounge_controller.refresh_auth()
                except BaseException:
                    await asyncio.sleep(10)
            while not (await self.is_available()) and not self.cancelled:
                await asyncio.sleep(10)
            try:
                await lounge_controller.connect()
            except BaseException:
                pass
            while not lounge_controller.connected() and not self.cancelled:
                # Doesn't connect to the device if it's a kids profile (it's broken)
                await asyncio.sleep(10)
                try:
                    await lounge_controller.connect()
                except BaseException:
                    pass
            self.logger.info(
                "Connected to device %s (%s)", lounge_controller.screen_name, self.name
            )
            try:
                self.logger.info("Subscribing to lounge")
                sub = await lounge_controller.subscribe_monitored(self)
                await sub
            except BaseException:
                pass

    # Method called on playback state change
    async def __call__(self, state):
        try:
            self.task.cancel()
        except BaseException:
            pass
        time_start = time.time()
        self.task = asyncio.create_task(self.process_playstatus(state, time_start))

    # Processes the playback state change
    async def process_playstatus(self, state, time_start):
        segments = []
        if state.videoId:
            segments = await self.api_helper.get_segments(state.videoId)
        if state.state.value == 1:  # Playing
            self.logger.info(
                f"Playing video {state.videoId} with {len(segments)} segments"
            )
            if segments:  # If there are segments
                await self.time_to_segment(segments, state.currentTime, time_start)

    # Finds the next segment to skip to and skips to it
    async def time_to_segment(self, segments, position, time_start):
        start_next_segment = None
        next_segment = None
        for segment in segments:
            if position < 2 and (segment["start"] <= position < segment["end"]):
                next_segment = segment
                start_next_segment = (
                    position  # different variable so segment doesn't change
                )
                break
            if segment["start"] > position:
                next_segment = segment
                start_next_segment = next_segment["start"]
                break
        if start_next_segment:
            time_to_next = (
                start_next_segment - position - (time.time() - time_start) - self.offset
            )
            await self.skip(time_to_next, next_segment["end"], next_segment["UUID"])

    # Skips to the next segment (waits for the time to pass)
    async def skip(self, time_to, position, uuids):
        await asyncio.sleep(time_to)
        self.logger.info("Skipping segment: seeking to %s", position)
        await asyncio.create_task(self.api_helper.mark_viewed_segments(uuids))
        await asyncio.create_task(self.lounge_controller.seek_to(position))

    async def cancel(self):
        """Cancel this device and clean up resources"""
        self.cancelled = True

        # Cancel and cleanup lounge controller
        if self.lounge_controller.connected():
            await self.lounge_controller.disconnect()

        # Cancel watchdog task if it exists and isn't done
        if (
            self.lounge_controller.watchdog_task
            and not self.lounge_controller.watchdog_task.done()
        ):
            self.lounge_controller.watchdog_task.cancel()

        # Cancel subscribe task if it exists and isn't done
        if (
            self.lounge_controller.subscribe_task
            and not self.lounge_controller.subscribe_task.done()
        ):
            self.lounge_controller.subscribe_task.cancel()

        # Cancel device task if it exists and isn't done
        if self.task and not self.task.done():
            self.task.cancel()

    async def initialize_web_session(self):
        await self.lounge_controller.change_web_session(self.web_session)
