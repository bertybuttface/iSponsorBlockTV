from hashlib import sha256

from aiohttp import ClientSession

from iSponsorBlockTV import constants
from iSponsorBlockTV.utils.cache import AsyncConditionalTTL, list_to_tuple


# Class that handles all the api calls and their cache
class ApiHelper:
    def __init__(self, config, web_session: ClientSession) -> None:
        self.apikey = config.apikey
        self.skip_categories = config.skip_categories
        self.skip_count_tracking = config.skip_count_tracking
        self.web_session = web_session
        self.num_devices = len(config.devices)

    @list_to_tuple  # Convert list to tuple so it can be used as a key in the cache
    @AsyncConditionalTTL(
        time_to_live=300, maxsize=10
    )  # 5 minutes for non-locked segments
    async def get_segments(self, vid_id):
        vid_id_hashed = sha256(vid_id.encode("utf-8")).hexdigest()[
            :4
        ]  # Hashes video id and gets the first 4 characters
        params = {
            "category": self.skip_categories,
            "actionType": constants.SponsorBlock_actiontype,
            "service": constants.SponsorBlock_service,
        }
        headers = {"Accept": "application/json"}
        url = constants.SponsorBlock_api + "skipSegments/" + vid_id_hashed
        async with self.web_session.get(
            url, headers=headers, params=params
        ) as response:
            response_json = await response.json()
        if response.status != 200:
            response_text = await response.text()
            print(
                f"Error getting segments for video {vid_id}, hashed as {vid_id_hashed}."
                f" Code: {response.status} - {response_text}"
            )
            return [], True
        for i in response_json:
            if str(i["videoID"]) == str(vid_id):
                response_json = i
                break
        return self.process_segments(response_json)

    @staticmethod
    def process_segments(response):
        segments = []
        ignore_ttl = True
        try:
            response_segments = response["segments"]
            # sort by end
            response_segments.sort(key=lambda x: x["segment"][1])
            # extend ends of overlapping segments to make one big segment
            for i in response_segments:
                for j in response_segments:
                    if j["segment"][0] <= i["segment"][1] <= j["segment"][1]:
                        i["segment"][1] = j["segment"][1]

            # sort by start
            response_segments.sort(key=lambda x: x["segment"][0])
            # extend starts of overlapping segments to make one big segment
            for i in reversed(response_segments):
                for j in reversed(response_segments):
                    if j["segment"][0] <= i["segment"][0] <= j["segment"][1]:
                        i["segment"][0] = j["segment"][0]

            for i in response_segments:
                ignore_ttl = (
                    ignore_ttl and i["locked"] == 1
                )  # If all segments are locked, ignore ttl
                segment = i["segment"]
                UUID = i["UUID"]
                segment_dict = {"start": segment[0], "end": segment[1], "UUID": [UUID]}
                try:
                    # Get segment before to check if they are too close to each other
                    segment_before_end = segments[-1]["end"]
                    segment_before_start = segments[-1]["start"]
                    segment_before_UUID = segments[-1]["UUID"]

                except Exception:
                    segment_before_end = -10
                if (
                    segment_dict["start"] - segment_before_end < 1
                ):  # Less than 1 second apart, combine them and skip them together
                    segment_dict["start"] = segment_before_start
                    segment_dict["UUID"].extend(segment_before_UUID)
                    segments.pop()
                segments.append(segment_dict)
        except Exception:
            pass
        return segments, ignore_ttl

    async def mark_viewed_segments(self, uuids):
        """Marks the segments as viewed in the SponsorBlock API, if skip_count_tracking is enabled.
        Lets the contributor know that someone skipped the segment (thanks)"""
        if self.skip_count_tracking:
            url = constants.SponsorBlock_api + "viewedVideoSponsorTime/"
            for i in uuids:
                params = {"UUID": i}
                await self.web_session.post(url, params=params)
