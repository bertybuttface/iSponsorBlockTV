from aiohttp import web
import aiohttp
import logging
from typing import Optional

from iSponsorBlockTV.core.youtube import YtLoungeApi
from iSponsorBlockTV.utils.config import Config

logger = logging.getLogger(__name__)

class SetupServer:
    def __init__(self, data_dir: str):
        self.config = Config.load(data_dir)
        self.app = web.Application()
        self.setup_routes()
        self.web_session: Optional[aiohttp.ClientSession] = None

    def setup_routes(self):
        self.app.router.add_get('/', self.serve_setup_page)
        self.app.router.add_get('/config', self.get_config)
        self.app.router.add_post('/pair', self.pair_device)
        self.app.router.add_post('/update', self.update_config)
        
    async def serve_setup_page(self, request: web.Request) -> web.Response:
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>iSponsorBlockTV Setup</title>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/semantic-ui@2.3.3/dist/semantic.min.css">
            <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/semantic-ui@2.3.3/dist/semantic.min.js"></script>
        </head>
        <body>
            <div class="ui container" style="padding: 2em 0;">
                <h1 class="ui header">iSponsorBlockTV Setup</h1>
                
                <div class="ui segment">
                    <h2 class="ui header">Devices</h2>
                    <h3> Pair a new device </h3>
                    <p>Enter the pairing code from your TV's YouTube app (Settings - Link with TV code)</p>
                    <div class="ui fluid action input">
                        <input type="text" id="pairingCode" placeholder="Enter pairing code">
                        <button class="ui primary button" onclick="pairDevice()">Pair Device</button>
                    </div>
                    <div id="pairResult" style="margin-top: 1em;"></div>
                    <h3 class="ui header">Paired Devices</h3>
                    <p>These devices are already paired. They are loaded from the config file. You can delete them if you wish</p>
                    <div class="ui divided list" id="devicesList">
                        <!-- Devices will be populated here -->
                    </div>
                </div>

                <div class="ui segment">
                    <h2 class="ui header">Configuration</h2>
                    
                    <h3 class="ui header">Skip Categories</h3>
                    <div class="ui fluid multiple selection dropdown" id="categoriesDropdown">
                        <input type="hidden" id="skipCategories">
                        <i class="dropdown icon"></i>
                        <div class="default text">Select categories to skip</div>
                        <div class="menu">
                            <div class="item" data-value="sponsor">Sponsor</div>
                            <div class="item" data-value="selfpromo">Self Promotion</div>
                            <div class="item" data-value="interaction">Interaction Reminder</div>
                            <div class="item" data-value="intro">Intro</div>
                            <div class="item" data-value="outro">Outro</div>
                            <div class="item" data-value="preview">Preview</div>
                            <div class="item" data-value="music_offtopic">Music: Non-Music</div>
                            <div class="item" data-value="filler">Filler</div>
                        </div>
                    </div>

                    <h3 class="ui header">Options</h3>
                    <div class="ui form">
                        <div class="field">
                            <div class="ui toggle checkbox">
                                <input type="checkbox" id="skipCountTracking" checked>
                                <label>Report skipped segments</label>
                            </div>
                        </div>
                        <div class="field">
                            <div class="ui toggle checkbox">
                                <input type="checkbox" id="muteAds">
                                <label>Mute ads</label>
                            </div>
                        </div>
                        <div class="field">
                            <div class="ui toggle checkbox">
                                <input type="checkbox" id="skipAds">
                                <label>Skip ads</label>
                            </div>
                        </div>
                        <div class="field">
                            <div class="ui toggle checkbox">
                                <input type="checkbox" id="autoPlay" checked>
                                <label>Enable autoplay</label>
                            </div>
                        </div>
                    </div>

                    <h3 class="ui header">YouTube API Key (Optional, only needed for channel whitelisting)</h3>
                    <div class="ui fluid input">
                        <input type="text" id="apiKey" placeholder="Enter YouTube API key">
                    </div>

                    <button class="ui primary button" onclick="saveConfig()" style="margin-top: 1em;">
                        Save Configuration
                    </button>
                    <div id="saveResult" style="margin-top: 1em;"></div>
                </div>
            </div>

            <script>
                // Initialize Semantic UI components
                $('.ui.dropdown').dropdown();
                $('.ui.checkbox').checkbox();

                // Load current config on page load
                fetch('/config')
                    .then(response => response.json())
                    .then(config => {
                        $('#skipCountTracking').prop('checked', config.skip_count_tracking);
                        $('#muteAds').prop('checked', config.mute_ads);
                        $('#skipAds').prop('checked', config.skip_ads);
                        $('#autoPlay').prop('checked', config.auto_play);
                        $('#apiKey').val(config.apikey || '');
                        
                        const categories = config.skip_categories || [];
                        $('#categoriesDropdown').dropdown('set selected', categories);

                        // Update devices list
                        const devicesList = $('#devicesList');
                        devicesList.empty();
                        
                        if (config.devices && config.devices.length > 0) {
                            config.devices.forEach(device => {
                                devicesList.append(`
                                    <div class="item">
                                        <div class="content">
                                            <div class="header">${device.name} (${device.screen_id})</div>
                                        </div>
                                    </div>
                                `);
                            });
                        } else {
                            devicesList.append(`
                                <div class="item">
                                    <div class="content">
                                        <div class="header">No devices paired</div>
                                    </div>
                                </div>
                            `);
                        }
                        
                        // Refresh UI state
                        $('.ui.checkbox').checkbox('refresh');
                    });

                async function pairDevice() {
                    const code = $('#pairingCode').val();
                    const resultDiv = $('#pairResult');
                    
                    try {
                        const response = await fetch('/pair', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({pairing_code: code})
                        });
                        const data = await response.json();
                        if (response.ok) {
                            resultDiv.html(`
                                <div class="ui positive message">
                                    <p>Successfully paired with ${data.device.name}</p>
                                </div>
                            `);
                            // Refresh the config to update the devices list
                            fetch('/config')
                                .then(response => response.json())
                                .then(config => {
                                    const devicesList = $('#devicesList');
                                    devicesList.empty();
                                    
                                    if (config.devices && config.devices.length > 0) {
                                        config.devices.forEach(device => {
                                            devicesList.append(`
                                                <div class="item">
                                                    <div class="content">
                                                        <div class="header">${device.name}</div>
                                                    </div>
                                                </div>
                                            `);
                                        });
                                    } else {
                                        devicesList.append(`
                                            <div class="item">
                                                <div class="content">
                                                    <div class="header">No devices paired</div>
                                                </div>
                                            </div>
                                        `);
                                    }
                                });
                        } else {
                            resultDiv.html(`
                                <div class="ui negative message">
                                    <p>${data.error || 'Failed to pair device'}</p>
                                </div>
                            `);
                        }
                    } catch (error) {
                        resultDiv.html(`
                            <div class="ui negative message">
                                <p>Failed to pair device: ${error}</p>
                            </div>
                        `);
                    }
                }

                async function saveConfig() {
                    const config = {
                        skip_categories: $('#categoriesDropdown').dropdown('get value').split(','),
                        skip_count_tracking: $('#skipCountTracking').prop('checked'),
                        mute_ads: $('#muteAds').prop('checked'),
                        skip_ads: $('#skipAds').prop('checked'),
                        auto_play: $('#autoPlay').prop('checked'),
                        apikey: $('#apiKey').val()
                    };

                    const resultDiv = $('#saveResult');
                    
                    try {
                        const response = await fetch('/update', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(config)
                        });
                        
                        if (response.ok) {
                            resultDiv.html(`
                                <div class="ui positive message">
                                    <p>Configuration saved successfully</p>
                                </div>
                            `);
                        } else {
                            const data = await response.json();
                            resultDiv.html(`
                                <div class="ui negative message">
                                    <p>${data.error || 'Failed to save configuration'}</p>
                                </div>
                            `);
                        }
                    } catch (error) {
                        resultDiv.html(`
                            <div class="ui negative message">
                                <p>Failed to save configuration: ${error}</p>
                            </div>
                        `);
                    }
                }
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')

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
            pairing_code = str(data['pairing_code']).replace("-", "").replace(" ", "")
            
            lounge_controller = YtLoungeApi()
            await lounge_controller.change_web_session(self.web_session)
            
            paired = await lounge_controller.pair(int(pairing_code))
            if not paired:
                return web.json_response({"error": "Failed to pair device"}, status=400)
            
            device = {
                "screen_id": lounge_controller.auth.screen_id,
                "name": lounge_controller.screen_name,
            }
            
            self.config.devices.append(device)
            self.config.save()
            
            return web.json_response({"device": device})
            
        except Exception as e:
            logger.exception("Error pairing device")
            return web.json_response({"error": str(e)}, status=400)

    async def delete_device(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            screen_id = data.get('screen_id')
            
            self.config.devices = [d for d in self.config.devices if d.screen_id != screen_id]
            self.config.save()
            return web.json_response({"status": "success"})
            
        except Exception as e:
            logger.exception("Error deleting device")
            return web.json_response({"error": str(e)}, status=400)

    async def update_config(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            
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
