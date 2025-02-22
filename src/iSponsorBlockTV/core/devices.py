import asyncio
import logging
import time

from signal import SIGINT, SIGTERM, signal
from typing import List, Optional

import aiohttp

from iSponsorBlockTV.core.youtube import YtLoungeApi
from iSponsorBlockTV.core.sponsorblock import ApiHelper


class DeviceManager:
    def __init__(self, config, debug: bool = False):
        self.config = config
        self.debug = debug
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.tasks: List[asyncio.Task] = []
        self.devices: List[DeviceListener] = []
        self.web_session: Optional[aiohttp.ClientSession] = None
        self.tcp_connector: Optional[aiohttp.TCPConnector] = None
        self.api_helper: Optional[ApiHelper] = None
        
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)

    async def initialize(self):
        """Initialize network resources and create device listeners"""
        self.loop = asyncio.get_event_loop()
        if self.debug:
            self.loop.set_debug(True)
            
        self.tcp_connector = aiohttp.TCPConnector(ttl_dns_cache=300)
        self.web_session = aiohttp.ClientSession(connector=self.tcp_connector)
        self.api_helper = ApiHelper(self.config, self.web_session)

        # Initialize devices
        for device_config in self.config.devices:
            device = DeviceListener(
                self.api_helper, 
                self.config, 
                device_config, 
                self.debug,
                self.web_session
            )
            self.devices.append(device)
            await device.initialize_web_session()
            
            # Create device tasks
            self.tasks.append(self.loop.create_task(device.loop()))
            self.tasks.append(self.loop.create_task(device.refresh_auth_loop()))

    async def cleanup(self):
        """Clean up all resources"""
        # Cancel all device tasks
        await asyncio.gather(
            *(device.cancel() for device in self.devices), 
            return_exceptions=True
        )
        
        # Cancel all pending tasks
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Close network resources
        if self.web_session:
            await self.web_session.close()
        if self.tcp_connector:
            await self.tcp_connector.close()
        if self.loop:
            self.loop.close()

    def handle_signal(self, signum, frame):
        """Handle system signals"""
        raise KeyboardInterrupt()

    async def run_async(self):
        """Main async execution loop"""
        try:
            await self.initialize()
            
            # Set up signal handlers
            signal(SIGTERM, self.handle_signal)
            signal(SIGINT, self.handle_signal)
            
            # Wait for all tasks to complete
            await asyncio.gather(*self.tasks)
            
        except KeyboardInterrupt:
            print("Cancelling tasks and exiting...")
        finally:
            await self.cleanup()
            print("Exited")

    def run(self):
        """Main entry point"""
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.run_async())


class DeviceListener:
    def __init__(self, api_helper, config, device, debug: bool, web_session):
        self.task: Optional[asyncio.Task] = None
        self.api_helper = api_helper
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
        self.cancelled = True
        await self.lounge_controller.disconnect()
        if self.task:
            self.task.cancel()
        if self.lounge_controller.subscribe_task_watchdog:
            self.lounge_controller.subscribe_task_watchdog.cancel()
        if self.lounge_controller.subscribe_task:
            self.lounge_controller.subscribe_task.cancel()
        await asyncio.gather(
            self.task,
            self.lounge_controller.subscribe_task_watchdog,
            self.lounge_controller.subscribe_task,
            return_exceptions=True,
        )

    async def initialize_web_session(self):
        await self.lounge_controller.change_web_session(self.web_session)
