import sys
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

        # Patch SetupServer
        self.setup_server_patcher = mock.patch("iSponsorBlockTV.utils.cli.SetupServer")
        self.mock_setup_server = self.setup_server_patcher.start()
        self.patchers.append(self.setup_server_patcher)

        # Create mock server instance
        self.mock_server_instance = mock.MagicMock()
        self.mock_setup_server.return_value = self.mock_server_instance

        # Patch webbrowser.open
        self.webbrowser_patcher = mock.patch("iSponsorBlockTV.utils.cli.webbrowser")
        self.mock_webbrowser = self.webbrowser_patcher.start()
        self.patchers.append(self.webbrowser_patcher)

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
        self.mock_device_manager.assert_called_once_with(self.mock_config, False)

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
        self.mock_device_manager.assert_called_with(self.mock_config, True)

    def test_config_without_subcommand(self):
        """Test that 'config' without subcommand shows help."""
        result = self.runner.invoke(self.cli, ["config"])

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify help text is shown
        self.assertIn("Configure", result.output)

    def test_config_web_command(self):
        """Test 'config web' command with default options."""
        # Invoke CLI with config web command
        result = self.runner.invoke(
            self.cli, ["--data", self.data_dir, "config", "web"]
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify SetupServer was instantiated with data_dir
        self.mock_setup_server.assert_called_once_with(self.data_dir)

        # Verify webbrowser.open was called with the default URL
        self.mock_webbrowser.open.assert_called_once_with("http://localhost:8080")

        # Verify server.run was called with default options
        self.mock_server_instance.run.assert_called_once_with(
            host="localhost", port=8080
        )

    def test_config_web_with_options(self):
        """Test 'config web' with custom port and no-browser flag."""
        # Invoke CLI with options
        result = self.runner.invoke(
            self.cli,
            [
                "--data",
                self.data_dir,
                "config",
                "web",
                "--port",
                "9000",
                "--no-browser",
            ],
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify SetupServer was instantiated with data_dir
        self.mock_setup_server.assert_called_once_with(self.data_dir)

        # Verify webbrowser.open was NOT called
        self.mock_webbrowser.open.assert_not_called()

        # Verify server.run was called with custom port
        self.mock_server_instance.run.assert_called_once_with(
            host="localhost", port=9000
        )

    def test_config_list_command(self):
        """Test 'config list' command."""
        # Invoke CLI with config list command
        result = self.runner.invoke(
            self.cli, ["--data", self.data_dir, "config", "list"]
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

    def test_config_validate_command(self):
        """Test 'config validate' command."""
        # Invoke CLI with config validate command
        result = self.runner.invoke(
            self.cli, ["--data", self.data_dir, "config", "validate"]
        )

        # Verify exit code
        self.assertEqual(result.exit_code, 0)

        # Verify Config.load was called with data_dir
        self.mock_config_class.load.assert_called_with(self.data_dir)

        # Verify validate_config was called
        self.mock_config.validate_config.assert_called_once()

        # Verify success message was shown
        self.mock_click_echo.assert_called_with("Config valid if no errors shown.")

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
