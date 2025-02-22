from aiohttp import web
import aiohttp
import logging
from typing import Optional, Dict
import pathlib

from iSponsorBlockTV.core.youtube import YtLoungeApi
from iSponsorBlockTV.utils.config import Config

logger = logging.getLogger(__name__)

class SetupServer:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.config: Config = Config.load(data_dir)
        self.app = web.Application()
        self.setup_routes()
        self.web_session: Optional[aiohttp.ClientSession] = None
        
        # Load static resources
        static_dir = pathlib.Path(__file__).parent / "static"
        static_dir.mkdir(exist_ok=True)
        self.app.router.add_static('/static', static_dir)

    def setup_routes(self):
        self.app.router.add_get('/', self.serve_setup_page)
        self.app.router.add_get('/config', self.get_config)
        self.app.router.add_post('/pair', self.pair_device)
        self.app.router.add_post('/delete-device', self.delete_device)
        self.app.router.add_post('/update', self.update_config)
        
    async def serve_setup_page(self, request: web.Request) -> web.Response:
        with open(pathlib.Path(__file__).parent / "static" / "setup.html", "r") as f:
            return web.Response(text=f.read(), content_type='text/html')

    async def get_config(self, request: web.Request) -> web.Response:
        return web.json_response({
            'devices': [{'name': d.name, 'screen_id': d.screen_id} for d in self.config.devices],
            'apikey': self.config.apikey,
            'skip_categories': self.config.skip_categories,
            'skip_count_tracking': self.config.skip_count_tracking,
            'mute_ads': self.config.mute_ads,
            'skip_ads': self.config.skip_ads,
            'auto_play': self.config.auto_play
        })

    async def pair_device(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            pairing_code = str(data['pairing_code']).strip().replace("-", "").replace(" ", "")
            
            lounge_controller = YtLoungeApi()
            await lounge_controller.change_web_session(self.web_session)
            
            paired = await lounge_controller.pair(int(pairing_code))
            if not paired:
                return web.json_response({"error": "Failed to pair device"}, status=400)
            
            device: Dict = {
                "screen_id": lounge_controller.auth.screen_id,
                "name": lounge_controller.screen_name,
            }
            
            self.config.devices.append(device)
            self.config.save()
            
            return web.json_response({"device": device})
            
        except ValueError:
            return web.json_response({"error": "Invalid pairing code"}, status=400)
        except Exception as e:
            logger.exception("Error pairing device")
            return web.json_response({"error": str(e)}, status=400)

    async def delete_device(self, request: web.Request) -> web.Response:
        try:
            data: Dict = await request.json()
            screen_id = data.get('screen_id')
            
            if not screen_id:
                return web.json_response({"error": "Missing screen_id parameter"}, status=400)
                
            # Filter out the device with the given screen_id
            original_length = len(self.config.devices)
            self.config.devices = [d for d in self.config.devices if d.screen_id != screen_id]
            
            if len(self.config.devices) == original_length:
                return web.json_response({"error": "Device not found"}, status=404)
                
            self.config.save()
            return web.json_response({"status": "success"})
            
        except Exception as e:
            logger.exception("Error deleting device")
            return web.json_response({"error": str(e)}, status=400)

    async def update_config(self, request: web.Request) -> web.Response:
        try:
            data: Dict = await request.json()
            self.config.skip_categories = data.get('skip_categories', ['sponsor'])
            self.config.skip_count_tracking = data.get('skip_count_tracking', True)
            self.config.mute_ads = data.get('mute_ads', False)
            self.config.skip_ads = data.get('skip_ads', False)
            self.config.auto_play = data.get('auto_play', True)
            self.config.apikey = data.get('apikey', '')
            
            self.config.save()
            return web.json_response({"status": "success"})
            
        except Exception as e:
            logger.exception("Error updating config")
            return web.json_response({"error": str(e)}, status=400)

    async def startup(self):
        self.web_session = aiohttp.ClientSession()

    async def cleanup(self):
        if self.web_session:
            await self.web_session.close()

    def run(self, host='0.0.0.0', port=8080):
        self.app.on_startup.append(lambda _: self.startup())
        self.app.on_cleanup.append(lambda _: self.cleanup())
        web.run_app(self.app, host=host, port=port)

def main(data_dir: str):
    server = SetupServer(data_dir)
    server.run()
