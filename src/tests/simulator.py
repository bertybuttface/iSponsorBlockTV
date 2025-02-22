import asyncio
import json
import os
import tempfile
import threading
import time
from os import getenv
from typing import Dict, Optional

import aiohttp
from browserforge.fingerprints import Screen  # Use browserforge to avoid detection
from camoufox.async_api import AsyncCamoufox  # Wraps playwright to avoid detection
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from iSponsorBlockTV.core.youtube import YtLoungeApi
from iSponsorBlockTV.utils.cli import app_start

# Load environment variables
GOOGLE_USERNAME: str = getenv("GOOGLE_USERNAME")
if not GOOGLE_USERNAME:
    raise Exception("GOOGLE_USERNAME environment variable not set")
GOOGLE_PASSWORD: str = getenv("GOOGLE_PASSWORD")
if not GOOGLE_PASSWORD:
    raise Exception("GOOGLE_PASSWORD environment variable not set")
VIDEO_ID: str = getenv("VIDEO_ID")
if not VIDEO_ID:
    raise Exception("VIDEO_ID environment variable not set")


class Simulator:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context_tv: Optional[BrowserContext] = None
        self.tv_page: Optional[Page] = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-automation",
            ],
        )
        # TODO: preserve self.context_tv state across runs to avoid need to login to youtube constantly
        self.context_tv = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:87.0) Gecko/20100101 Cobalt/87.0"
        )
        self.context_ytbe = await self.browser.new_context()
        self.web_session = aiohttp.ClientSession()

        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp(prefix="isponsorblocktv_")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Stop the app thread if it exists
        if hasattr(self, "app_thread") and self.app_thread.is_alive():
            # TODO: might need a way to signal the app to shut down cleanly here, might not.
            self.app_thread.join(timeout=5)  # Wait up to 5 seconds for thread to finish

        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self.web_session:
            await self.web_session.close()
        # Clean up temporary directory
        try:
            import shutil

            if self.temp_dir:
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            print(
                f"Warning: Failed to clean up temporary directory {self.temp_dir}: {e}"
            )

    async def browse_to_tv_url(self) -> None:
        self.tv_page = await self.context_tv.new_page()
        await self.tv_page.goto("https://www.youtube.com/tv?hrld=1#/")

    async def check_if_we_are_logged_in(self) -> bool:
        # TODO: check for presence of self.tv_page.locator("text=Get started").first
        # If it exists return False if not return True
        return False

    async def get_youtube_tv_code(self) -> Optional[str]:
        """Get the YouTube TV pairing code."""
        try:
            # Click the "Get started" button
            button = self.tv_page.locator("text=Get started").first
            await button.click()

            # Wait for and get the code element
            code_element = self.tv_page.locator(
                '.ytLrOverlayMessageRendererSubtitle[aria-label*="."]'
            ).first
            # Optionally wait for the element to appear
            await code_element.wait_for(timeout=20000)
            code = await code_element.text_content()
            print(f"Found code: {code}")
            return code
        except Exception as e:
            print(f"Error getting YouTube TV code: {e}")
            return None

    async def pair_youtube_tv_code(self, youtube_tv_code: str) -> Optional[str]:
        """Pair the YouTube TV code and get the lounge code."""
        try:
            print(f"Pairing with YouTube TV code: {youtube_tv_code}")

            async with AsyncCamoufox(
                os=("windows", "macos", "linux"),
                screen=Screen(max_width=1920, max_height=1080),
            ) as browser:
                ytbe_page = await browser.new_page()
                await ytbe_page.goto("https://yt.be/activate")

                # Fill in the code input field
                await ytbe_page.fill('input[name="code"]', youtube_tv_code)

                # Click the Continue button
                await ytbe_page.click("text=Continue")

                # Fill in the email field
                await ytbe_page.fill("#identifierId", GOOGLE_USERNAME)

                # Click the Next button
                await ytbe_page.click("#identifierNext")

                # Fill in the password field
                await ytbe_page.fill('input[name="Passwd"]', GOOGLE_PASSWORD)

                # Click the Next button
                await ytbe_page.click("#passwordNext")

                # Wait for the "Approve access" button
                await ytbe_page.click("#submit_approve_access")

                # Close the browser
                await browser.close()

            return True

        except Exception as e:
            print(f"Error pairing YouTube TV code: {e}")
            return None

    async def get_ytlounge_code(self) -> Optional[str]:
        # Click settings button
        await self.tv_page.click('ytlr-guide-entry-renderer[aria-label="Settings"]')

        # Click Link with TV code
        await self.tv_page.click('yt-formatted-string:text("Link with TV code")')

        # Set a maximum wait time (e.g., 30 seconds)
        MAX_WAIT_TIME = 30
        start_time = time.time()

        # Wait until the text changes from "Loading..." or timeout occurs
        text = await self.tv_page.wait_for_selector(
            ".ytLrLinkPhoneWithTvCodeRendererPairingCodeText"
        )
        while True:
            if time.time() - start_time > MAX_WAIT_TIME:
                raise TimeoutError("Timed out waiting for TV code to appear")

            current_text = await text.inner_text()
            if "Loading" not in current_text and current_text != "":
                break
            await self.tv_page.wait_for_timeout(
                500
            )  # Wait half a second before checking again

        # Now get the final text (should be the code)
        ytlounge_code = await self.tv_page.locator(
            ".ytLrLinkPhoneWithTvCodeRendererPairingCodeText"
        ).inner_text()

        return ytlounge_code

    async def pair_with_ytlounge_code(self, yt_lounge_code: str) -> Optional[Dict]:
        """Pair with YtLoungeApi using the lounge code."""
        try:
            lounge_controller = YtLoungeApi()
            await lounge_controller.change_web_session(self.web_session)
            paired = await lounge_controller.pair(int(yt_lounge_code.replace(" ", "")))
            if not paired:
                print("Failed to pair device")
                return None

            return {
                "code": yt_lounge_code,
                "screen_id": lounge_controller.auth.screen_id,
                "name": lounge_controller.screen_name,
            }
        except Exception as e:
            print(f"Error pairing with YtLoungeApi: {e}")
            raise e
            # return None

    async def initialise_isponsorblocktv(self, device: Dict):
        """Initialise iSponsorBlockTV and run the test scenario."""

        self.config_dir = os.path.join(self.temp_dir, "config")
        self.config_path = os.path.join(self.config_dir, "config.json")

        # Default configuration
        default_config = {
            "devices": [device],  # Include the provided device
            "apikey": "",
            "skip_categories": [
                "sponsor",
                "selfpromo",
                "exclusive_access",
                "interaction",
                "preview",
                "filler",
                "music_offtopic",
                "intro",
                "outro",
            ],
            "skip_count_tracking": False,
            "mute_ads": False,
            "skip_ads": False,
            "auto_play": True,
            "join_name": "iSponsorBlockTV",
        }

        # Create config directory and save config.json
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(default_config, f, indent=2)

        # Run the isponsorblock app itself in a separate thread
        def run_app():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            os.environ["iSPBTV_data_dir"] = self.config_dir
            app_start()

        thread = threading.Thread(target=run_app)
        thread.start()

        # Store the thread so we can clean it up later in __aexit__
        self.app_thread = thread

        return True

    async def play_video(self, device: Dict):
        """Play a video on the device."""
        await self.tv_page.goto(
            f"https://www.youtube.com/tv?is_account_switch=1&hrld=2#/watch?v={VIDEO_ID}"
        )
        return True
        # TODO: return False if there is an error

    async def listen_for_skips(self, device: Dict):
        """Listen for sponsor segment skips."""
        # TODO: Implement this method
        pass


async def main():
    async with Simulator() as sim:
        # Browse to TV url
        await sim.browse_to_tv_url()

        # Check if we are logged in
        if not await sim.check_if_we_are_logged_in():
            # We are not logged in so we need to login
            print(f"We are not logged in, starting login and pair as {GOOGLE_USERNAME}")

            # Get the YouTube TV code
            code = await sim.get_youtube_tv_code()
            if not code:
                print("Failed to get YouTube TV code")
                return None

            # Pair the YouTube TV code
            pair_result = await sim.pair_youtube_tv_code(code)
            if not pair_result:
                print("Failed to pair YouTube TV code")
                return None
            else:
                print(f"Successfully paired YouTube TV code with {GOOGLE_USERNAME}")
        else:
            print("We are already logged in, can't tell which user but doesn't matter")

        # Get the ytlounge code
        lounge_code = await sim.get_ytlounge_code()
        if not lounge_code:
            print("Failed to get ytlounge code")
            return None
        else:
            print(f"Found lounge code: {lounge_code}")

        # Pair with YtLoungeApi
        device = await sim.pair_with_ytlounge_code(lounge_code)
        if not device:
            print("Failed to pair device")
            return None
        else:
            print(f"Successfully paired device: {device}")

        # Initialise iSponsorBlockTV
        init_result = await sim.initialise_isponsorblocktv(device)
        if not init_result:
            print("Failed to initialise iSponsorBlockTV")
            return None
        else:
            print("Successfully initialised iSponsorBlockTV")

        # Play a video
        video_result = await sim.play_video(device)
        if not video_result:
            print("Failed to play video")
            return None
        else:
            print("Successfully played video")

        # Pause until user presses Enter
        await asyncio.get_event_loop().run_in_executor(
            None, input, "Press Enter to continue..."
        )

        # Listen for sponsor segment skips
        skips_result = await sim.listen_for_skips(device)
        if not skips_result:
            print("Failed to listen for skips")
            return None
        else:
            print("Successfully listened for skips")

        return device


if __name__ == "__main__":
    device = asyncio.run(main())
    if device:
        print(f"Final device info: {device}")
    else:
        print("Process failed")
