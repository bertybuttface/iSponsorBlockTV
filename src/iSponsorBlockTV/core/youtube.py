import json
from asyncio import CancelledError, Task, create_task, sleep
from logging import Logger
from typing import Any, Callable, Dict, List, Optional

import pyytlounge
from aiohttp import ClientSession

from iSponsorBlockTV.constants import youtube_client_blacklist


class YtLoungeApi(pyytlounge.YtLoungeApi):
    def __init__(
        self,
        screen_id=None,
        config=None,
        api_helper=None,
        logger=None,
    ):
        super().__init__(
            config.join_name if config else "iSponsorBlockTV", logger=logger
        )
        self.auth.screen_id = screen_id
        self.auth.lounge_id_token = None
        self.api_helper = api_helper
        self.volume_state: Dict[str, Any] = {}
        self.subscribe_task: Optional[Task] = None
        self.watchdog_task: Optional[Task] = None
        self.callback: Optional[Callable] = None
        self.logger: Optional[Logger] = logger
        self.shorts_disconnected = False
        self.auto_play = True
        if config:
            self.mute_ads = config.mute_ads
            self.skip_ads = config.skip_ads
            self.auto_play = config.auto_play

    # Ensures that we still are subscribed to the lounge
    async def _watchdog(self):
        try:
            await sleep(35)  # YouTube sends at least one message every 30s
            self.logger.debug("Watchdog timeout - restarting subscription")
            if self.subscribe_task:
                self.subscribe_task.cancel()
                self.subscribe_task = create_task(super().subscribe(self.callback))
        except CancelledError:
            # Normal when watchdog is reset due to activity
            pass

    # Reset the watchdog timer
    def _reset_watchdog(self):
        if self.watchdog_task:
            self.watchdog_task.cancel()
        self.watchdog_task = create_task(self._watchdog())

    # Subscribe to the lounge and start the watchdog
    async def subscribe_monitored(self, callback):
        self.callback = callback
        self.logger.debug("Starting subscription with watchdog")
        self.subscribe_task = create_task(super().subscribe(callback))
        self._reset_watchdog()
        return self.subscribe_task

    # Process a lounge subscription event
    def _process_event(self, event_type: str, args: List[Any]):
        self.logger.debug(f"process_event({event_type}, {args})")
        # Reset the watchdog on each event
        self._reset_watchdog()
        # Events to detect ads playing & the next video before it starts playing (so we can get the segments)
        if event_type == "onStateChange":
            data = args[0]
            # print(data)
            # Unmute when the video starts playing
            if self.mute_ads and data["state"] == "1":
                create_task(self.mute(False, override=True))
        elif event_type == "nowPlaying":
            data = args[0]
            # Unmute when the video starts playing
            if self.mute_ads and data.get("state", "0") == "1":
                self.logger.info("Ad has ended, unmuting")
                create_task(self.mute(False, override=True))
        elif event_type == "onAdStateChange":
            data = args[0]
            if data["adState"] == "0":  # Ad is not playing
                self.logger.info("Ad has ended, unmuting")
                create_task(self.mute(False, override=True))
            elif (
                self.skip_ads and data["isSkipEnabled"] == "true"
            ):  # YouTube uses strings for booleans
                self.logger.info("Ad can be skipped, skipping")
                create_task(self.skip_ad())
                create_task(self.mute(False, override=True))
            elif (
                self.mute_ads
            ):  # Seen multiple other adStates, assuming they are all ads
                self.logger.info("Ad has started, muting")
                create_task(self.mute(True, override=True))
        # Manages volume, useful since YouTube wants to know the volume when unmuting (even if they already have it)
        elif event_type == "onVolumeChanged":
            self.volume_state = args[0]
        # Gets segments for the next video before it starts playing
        elif event_type == "autoplayUpNext":
            if len(args) > 0 and (vid_id := args[0].get("videoId")):
                # video id is not empty
                self.logger.info(f"Getting segments for next video: {vid_id}")
                create_task(self.api_helper.get_segments(vid_id))

        # Used to know if an ad is skippable or not
        elif event_type == "adPlaying":
            data = args[0]
            # Gets segments for the next video (after the ad) before it starts playing
            if vid_id := data.get("contentVideoId"):
                self.logger.info(f"Getting segments for next video: {vid_id}")
                create_task(self.api_helper.get_segments(vid_id))
            elif (
                self.skip_ads and data.get("isSkipEnabled") == "true"
            ):  # YouTube uses strings for booleans
                self.logger.info("Ad can be skipped, skipping")
                create_task(self.skip_ad())
                create_task(self.mute(False, override=True))
            elif (
                self.mute_ads
            ):  # Seen multiple other adStates, assuming they are all ads
                self.logger.info("Ad has started, muting")
                create_task(self.mute(True, override=True))

        elif event_type == "loungeStatus":
            data = args[0]
            devices = json.loads(data["devices"])
            for device in devices:
                if device["type"] == "LOUNGE_SCREEN":
                    device_info = json.loads(device.get("deviceInfo", "{}"))
                    if device_info.get("clientName", "") in youtube_client_blacklist:
                        self._sid = None
                        self._gsession = None  # Force disconnect

        elif event_type == "onSubtitlesTrackChanged":
            if self.shorts_disconnected:
                data = args[0]
                video_id_saved = data.get("videoId")
                self.shorts_disconnected = False
                if video_id_saved:
                    create_task(self.play_video(video_id_saved))
        elif event_type == "loungeScreenDisconnected":
            if args:  # Sometimes it's empty
                data = args[0]
                if data.get("reason") == "disconnectedByUserScreenInitiated":
                    # Short playing
                    self.shorts_disconnected = True
        elif event_type == "onAutoplayModeChanged":
            create_task(self.set_auto_play_mode(self.auto_play))

        super()._process_event(event_type, args)

    # Set the volume to a specific value (0-100)
    async def set_volume(self, volume: int) -> None:
        await super()._command("setVolume", {"volume": volume})

    # Mute/unmute device (no action if already in target state)
    # mute: True=mute, False=unmute
    # override: True=send command regardless of current state
    # TODO: Only works if the device is subscribed to the lounge
    async def mute(self, mute: bool, override: bool = False) -> None:
        mute_str = "true" if mute else "false"
        if override or self.volume_state.get("muted", "false") != mute_str:
            self.volume_state["muted"] = mute_str
            # YouTube wants the volume when unmuting, so we send it
            await super()._command(
                "setVolume",
                {"volume": self.volume_state.get("volume", 100), "muted": mute_str},
            )

    async def set_auto_play_mode(self, enabled: bool) -> None:
        await super()._command(
            "setAutoplayMode", {"autoplayMode": "ENABLED" if enabled else "DISABLED"}
        )

    async def change_web_session(self, web_session: ClientSession) -> None:
        if self.session is not None:
            await self.session.close()
        if self.conn is not None:
            await self.conn.close()
        self.session = web_session
