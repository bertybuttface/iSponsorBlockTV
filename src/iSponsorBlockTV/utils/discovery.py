"""Send out an M-SEARCH request and listening for responses. See LICENSE.md
Modified code from https://github.com/codingjoe/ssdp/blob/main/ssdp/__main__.py"""

import asyncio
import socket

import ssdp
import xmltodict
from ssdp import network


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class Handler(ssdp.aio.SSDP):
    def __init__(self):
        super().__init__()
        self.devices = []

    def clear(self):
        self.devices = []

    def __call__(self):
        return self

    def response_received(self, response: ssdp.messages.SSDPResponse, addr):
        headers = response.headers
        headers = {k.lower(): v for k, v in headers}
        # print(headers)
        if "location" in headers:
            self.devices.append(headers["location"])


async def find_youtube_app(web_session, url_location):
    async with web_session.get(url_location) as response:
        headers = response.headers
        response = await response.text()
    # print(headers)

    data = xmltodict.parse(response)
    name = data["root"]["device"]["friendlyName"]
    handler = Handler()
    handler.clear()
    app_url = headers["application-url"]
    youtube_url = app_url + "YouTube"
    # print(youtube_url)
    async with web_session.get(youtube_url) as response:
        status_code = response.status
        response = await response.text()
        # print(status_code)
    if status_code == 200:
        data = xmltodict.parse(response)
        data = data["service"]
        screen_id = data["additionalData"]["screenId"]
        return {"screen_id": screen_id, "name": name, "offset": 0}


async def discover(
    web_session,
    bind=None,
    search_target="urn:dial-multiscreen-org:service:dial:1",
    max_wait=10,
):
    handler = Handler()
    """Send out an M-SEARCH request and listening for responses."""
    family, addr = network.get_best_family(bind, network.PORT)
    loop = asyncio.get_event_loop()
    ip_address = get_ip()
    connect = loop.create_datagram_endpoint(
        handler, family=family, local_addr=(ip_address, None)
    )
    transport, protocol = await connect

    target = network.MULTICAST_ADDRESS_IPV4, network.PORT

    search_request = ssdp.messages.SSDPRequest(
        "M-SEARCH",
        headers={
            "HOST": "%s:%d" % target,
            "MAN": '"ssdp:discover"',
            "MX": str(max_wait),  # seconds to delay response [1..5]
            "ST": search_target,
        },
    )

    target = network.MULTICAST_ADDRESS_IPV4, network.PORT

    search_request.sendto(transport, target)

    # print(search_request, addr[:2])
    try:
        await asyncio.sleep(4)
    finally:
        transport.close()

    devices = []
    for i in handler.devices:
        devices.append(await find_youtube_app(web_session, i))

    return devices
