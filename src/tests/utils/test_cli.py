import tempfile
import unittest
from unittest import mock

from click.testing import CliRunner


class TestCLI(unittest.TestCase):
    def setUp(self):
        # Create a testing CLI runner
        self.runner = CliRunner(mix_stderr=False)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = self.temp_dir.name

        # Set up patchers
        self.patchers = []

        # First, patch the Config class
        self.config_patcher = mock.patch("iSponsorBlockTV.utils.cli.Config")
        self.mock_config_class = self.config_patcher.start()
        self.patchers.append(self.config_patcher)

        # Mock load method and config instance
        self.mock_config = mock.MagicMock()
        self.mock_config.devices = [mock.MagicMock()]
        self.mock_config.skip_categories = ["sponsor", "intro"]
        self.mock_config.skip_count_tracking = True
        self.mock_config.mute_ads = False
        self.mock_config.skip_ads = True
        self.mock_config.auto_play = True

        # Set up Config.load to return our mock config
        self.mock_config_class.load.return_value = self.mock_config

        # Patch DeviceManager
        self.device_mgr_patcher = mock.patch("iSponsorBlockTV.utils.cli.DeviceManager")
        self.mock_device_manager = self.device_mgr_patcher.start()
        self.patchers.append(self.device_mgr_patcher)

        # Create mock device manager instance
        self.mock_device_manager_instance = mock.MagicMock()
        self.mock_device_manager.return_value = self.mock_device_manager_instance

        # Patch run_web_server
        self.web_server_patcher = mock.patch("iSponsorBlockTV.utils.cli.run_web_server")
        self.mock_run_web_server = self.web_server_patcher.start()
        self.patchers.append(self.web_server_patcher)

        # Patch multiprocessing.Process
        self.process_patcher = mock.patch("multiprocessing.Process")
        self.mock_process = self.process_patcher.start()
        self.patchers.append(self.process_patcher)

        # Mock Process instance
        self.mock_process_instance = mock.MagicMock()
        self.mock_process.return_value = self.mock_process_instance

        # Patch logging.basicConfig
        self.logging_patcher = mock.patch("iSponsorBlockTV.utils.cli.logging")
        self.mock_logging = self.logging_patcher.start()
        self.patchers.append(self.logging_patcher)

        # Patch click.echo
        self.click_echo_patcher = mock.patch("iSponsorBlockTV.utils.cli.click.echo")
        self.mock_click_echo = self.click_echo_patcher.start()
        self.patchers.append(self.click_echo_patcher)

        # Import the CLI function to test after patching
        from iSponsorBlockTV.utils.cli import cli

        self.cli = cli

    def tearDown(self):
        # Stop all patchers
        for patcher in self.patchers:
            patcher.stop()
        self.temp_dir.cleanup()

    def test_start_command(self):
        """Test that start command initializes and runs a DeviceManager."""
        # Invoke CLI with start command
        result = self.runner.invoke(self.cli, ["--data", self.data_dir, "start"])

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify Config.load was called with data_dir
        self.mock_config_class.load.assert_called_with(self.data_dir)

        # Verify validate_config was called
        self.mock_config.validate_config.assert_called_once()

        # Verify DeviceManager was initialized with correct args
        self.mock_device_manager.assert_called_once_with(
            self.mock_config, False, watch_config=False
        )

        # Verify run was called
        self.mock_device_manager_instance.run.assert_called_once()

    def test_debug_flag(self):
        """Test that --debug flag sets up logging and passes debug=True."""
        # Invoke CLI with debug flag
        result = self.runner.invoke(
            self.cli, ["--data", self.data_dir, "--debug", "start"]
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify logging was configured
        self.mock_logging.basicConfig.assert_called_once()

        # Verify DeviceManager was created with debug=True
        self.mock_device_manager.assert_called_with(
            self.mock_config, True, watch_config=False
        )

    def test_web_flag(self):
        """Test that --web flag starts both the web server and main app."""
        # Invoke CLI with web flag
        result = self.runner.invoke(
            self.cli, ["--data", self.data_dir, "--web", "start"]
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify Process was created for the web server
        self.mock_process.assert_called_once()
        self.mock_process_instance.start.assert_called_once()
        
        # Verify watch_config is automatically enabled
        self.mock_device_manager.assert_called_with(
            self.mock_config, False, watch_config=True
        )

    def test_web_flag_with_port(self):
        """Test that --web flag with custom port works."""
        # Invoke CLI with web flag and custom port
        result = self.runner.invoke(
            self.cli, ["--data", self.data_dir, "--web", "--port", "9000", "start"]
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify Process was created with the custom port
        args = self.mock_process.call_args[1]["args"]
        self.assertEqual(args[1], 9000)  # Second arg should be the port

    def test_web_command(self):
        """Test 'web' command with default options."""
        # Invoke CLI with web command
        result = self.runner.invoke(
            self.cli, ["--data", self.data_dir, "web"]
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify run_web_server was called with correct args
        self.mock_run_web_server.assert_called_once_with(
            self.data_dir, 8080, False  # default port, no-browser=False
        )

    def test_web_command_with_options(self):
        """Test 'web' command with custom port and no-browser flag."""
        # Invoke CLI with web command and options
        result = self.runner.invoke(
            self.cli,
            ["--data", self.data_dir, "web", "--port", "9000", "--no-browser"]
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify run_web_server was called with correct args
        self.mock_run_web_server.assert_called_once_with(
            self.data_dir, 9000, True  # custom port, no-browser=True
        )

    def test_info_command(self):
        """Test 'info' command."""
        # Invoke CLI with info command
        result = self.runner.invoke(
            self.cli, ["--data", self.data_dir, "info"]
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify Config.load was called with data_dir
        self.mock_config_class.load.assert_called_with(self.data_dir)

        # Verify click.echo was called with config info
        # Check a few key pieces of data
        self.mock_click_echo.assert_any_call(f"Data directory: {self.data_dir}")
        self.mock_click_echo.assert_any_call(
            f"Devices: {len(self.mock_config.devices)}"
        )

    def test_watch_config_flag(self):
        """Test that --watch-config flag enables config watching."""
        # Invoke CLI with watch-config flag
        result = self.runner.invoke(
            self.cli, ["--data", self.data_dir, "--watch-config", "start"]
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify DeviceManager was created with watch_config=True
        self.mock_device_manager.assert_called_with(
            self.mock_config, False, watch_config=True
        )

    @mock.patch("iSponsorBlockTV.utils.cli.cli")
    def test_app_start(self, mock_cli):
        """Test app_start function."""
        from iSponsorBlockTV.utils.cli import app_start

        app_start()
        mock_cli.assert_called_once_with(obj={})

    @mock.patch("iSponsorBlockTV.utils.cli.app_start")
    def test_main(self, mock_app_start):
        """Test main function."""
        from iSponsorBlockTV.__main__ import main

        main()
        mock_app_start.assert_called_once()
