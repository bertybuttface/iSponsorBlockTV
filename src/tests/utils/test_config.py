import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

from iSponsorBlockTV.utils.config import Config, Device


class TestDevice(unittest.TestCase):
    """Tests for the Device model class."""

    def test_valid_device(self):
        """Test creating a valid Device instance."""
        device = Device(screen_id="screen123", name="Test Device", offset=1000)
        self.assertEqual(device.screen_id, "screen123")
        self.assertEqual(device.name, "Test Device")
        self.assertEqual(device.offset, 1.0)  # Converted from ms to seconds

    def test_empty_screen_id(self):
        """Test that empty screen_id raises validation error."""
        with self.assertRaises(ValidationError):
            Device(screen_id="", name="Test Device")

    def test_whitespace_screen_id(self):
        """Test that whitespace-only screen_id raises validation error."""
        with self.assertRaises(ValidationError):
            Device(screen_id="   ", name="Test Device")

    def test_convert_offset_to_seconds(self):
        """Test that offset is converted from milliseconds to seconds."""
        device = Device(screen_id="screen123", offset=2500)
        self.assertEqual(device.offset, 2.5)

    def test_default_values(self):
        """Test default values for optional fields."""
        device = Device(screen_id="screen123")
        self.assertEqual(device.name, "")
        self.assertEqual(device.offset, 0.0)


class TestConfig(unittest.TestCase):
    """Tests for the Config class."""

    def setUp(self):
        """Set up a temporary directory for config files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.config_file = self.data_dir / "config.json"

    def tearDown(self):
        """Clean up temporary files."""
        self.temp_dir.cleanup()

    def test_create_default_config(self):
        """Test creating a default config instance."""
        config = Config(data_dir=self.data_dir)
        self.assertEqual(config.data_dir, self.data_dir)
        self.assertEqual(config.devices, [])
        self.assertEqual(config.skip_categories, ["sponsor"])
        self.assertTrue(config.skip_count_tracking)
        self.assertFalse(config.mute_ads)
        self.assertFalse(config.skip_ads)
        self.assertTrue(config.auto_play)
        self.assertEqual(config.join_name, "iSponsorBlockTV")

    def test_config_file_property(self):
        """Test the config_file property."""
        config = Config(data_dir=self.data_dir)
        self.assertEqual(config.config_file, self.data_dir / "config.json")

    def test_load_from_nonexistent_file(self):
        """Test loading config from a non-existent file returns default config."""
        # Ensure the file doesn't exist
        if self.config_file.exists():
            self.config_file.unlink()

        config = Config.load(self.data_dir)
        self.assertEqual(config.data_dir, self.data_dir)
        self.assertEqual(config.devices, [])

    def test_load_from_valid_json_file(self):
        """Test loading config from a valid JSON file."""
        # Create a valid config file
        config_data = {
            "devices": [{"screen_id": "test123", "name": "Test Device", "offset": 500}],
            "apikey": "testkey",
            "skip_categories": ["sponsor", "intro"],
            "skip_count_tracking": False,
            "mute_ads": True,
            "skip_ads": True,
            "auto_play": False,
            "join_name": "TestTV",
        }
        self.config_file.write_text(json.dumps(config_data))

        # Load the config
        config = Config.load(self.data_dir)

        # Verify loaded values
        self.assertEqual(len(config.devices), 1)
        self.assertEqual(config.devices[0].screen_id, "test123")
        self.assertEqual(config.devices[0].name, "Test Device")
        self.assertEqual(config.devices[0].offset, 0.5)  # Converted to seconds
        self.assertEqual(config.apikey, "testkey")
        self.assertEqual(config.skip_categories, ["sponsor", "intro"])
        self.assertFalse(config.skip_count_tracking)
        self.assertTrue(config.mute_ads)
        self.assertTrue(config.skip_ads)
        self.assertFalse(config.auto_play)
        self.assertEqual(config.join_name, "TestTV")

    def test_load_from_invalid_json_file(self):
        """Test loading config from an invalid JSON file raises appropriate error."""
        # Create an invalid JSON file
        self.config_file.write_text("This is not valid JSON")

        # Mock _exit_with_message to prevent actual exit
        with mock.patch.object(Config, "_exit_with_message") as mock_exit:
            Config.load(self.data_dir)
            mock_exit.assert_called_once_with("Invalid JSON")

    def test_save_config(self):
        """Test saving config to file."""
        # Create a config with custom values
        config = Config(
            data_dir=self.data_dir,
            devices=[Device(screen_id="test123", name="Test Device")],
            apikey="testkey",
            skip_categories=["sponsor", "intro"],
            skip_count_tracking=False,
            mute_ads=True,
            skip_ads=True,
            auto_play=False,
            join_name="TestTV",
        )

        # Save the config
        config.save()

        # Verify the file was created
        self.assertTrue(self.config_file.exists())

        # Load the file and verify content
        with open(self.config_file, "r") as f:
            saved_data = json.load(f)

        # Verify the saved values
        self.assertEqual(len(saved_data["devices"]), 1)
        self.assertEqual(saved_data["devices"][0]["screen_id"], "test123")
        self.assertEqual(saved_data["devices"][0]["name"], "Test Device")
        self.assertEqual(saved_data["apikey"], "testkey")
        self.assertEqual(saved_data["skip_categories"], ["sponsor", "intro"])
        self.assertFalse(saved_data["skip_count_tracking"])
        self.assertTrue(saved_data["mute_ads"])
        self.assertTrue(saved_data["skip_ads"])
        self.assertFalse(saved_data["auto_play"])
        self.assertEqual(saved_data["join_name"], "TestTV")

    def test_save_config_io_error(self):
        """Test handling of IO errors during config save."""
        config = Config(data_dir=self.data_dir)

        # Mock write_text to raise IOError
        with mock.patch.object(Path, "write_text") as mock_write:
            mock_write.side_effect = IOError("Test IO error")

            # Mock logging to check the error is logged
            with mock.patch("iSponsorBlockTV.utils.config.logger.error") as mock_log:
                config.save()
                mock_log.assert_called_once()
                self.assertIn("Failed to save configuration", mock_log.call_args[0][0])

    def test_load_json_method(self):
        """Test the load_json method."""
        json_str = json.dumps(
            {
                "devices": [{"screen_id": "test123", "name": "Test Device"}],
                "apikey": "testkey",
            }
        )

        config = Config.load_json(json_str, self.data_dir)

        self.assertEqual(config.data_dir, self.data_dir)
        self.assertEqual(len(config.devices), 1)
        self.assertEqual(config.devices[0].screen_id, "test123")
        self.assertEqual(config.apikey, "testkey")

    def test_load_dict_method(self):
        """Test the load_dict method."""
        data_dict = {
            "devices": [{"screen_id": "test123", "name": "Test Device"}],
            "apikey": "testkey",
            "config_file": "should_be_filtered",  # Should be filtered out
        }

        config = Config.load_dict(data_dict, self.data_dir)

        self.assertEqual(config.data_dir, self.data_dir)
        self.assertEqual(len(config.devices), 1)
        self.assertEqual(config.devices[0].screen_id, "test123")
        self.assertEqual(config.apikey, "testkey")
        # Verify filtered keys
        self.assertNotEqual(config.config_file, "should_be_filtered")
        self.assertEqual(config.config_file, self.data_dir / "config.json")

    @mock.patch("iSponsorBlockTV.utils.config.Config._exit_with_message")
    def test_validate_config_no_devices(self, mock_exit):
        """Test validate_config when no devices are configured."""
        config = Config(data_dir=self.data_dir)
        config.validate_config()
        mock_exit.assert_called_once_with(
            "No devices found, please add at least one device"
        )

    @mock.patch("iSponsorBlockTV.utils.config.Config._exit_with_message")
    def test_validate_config_with_atvs_deprecated(self, mock_exit):
        """Test validate_config when the deprecated 'atvs' property is present."""
        config = Config(data_dir=self.data_dir)
        # Add a device to prevent the "no devices" error
        config.devices = [Device(screen_id="test123")]
        # Add the deprecated property
        config.__dict__["atvs"] = []

        config.validate_config()

        # Should exit with a deprecation message
        mock_exit.assert_called_once()
        self.assertIn("'atvs' config option is deprecated", mock_exit.call_args[0][0])

    @mock.patch("iSponsorBlockTV.utils.config.Config._exit_with_message")
    @mock.patch("iSponsorBlockTV.utils.config.Config._is_docker")
    def test_handle_missing_config_in_docker(self, mock_is_docker, mock_exit):
        """Test _handle_missing_config when running in Docker."""
        mock_is_docker.return_value = True

        # Create a config with a non-existent data_dir
        config = Config(data_dir=Path("/nonexistent/dir"))

        # Mock Path.exists to return False
        with mock.patch.object(Path, "exists", return_value=False):
            config._handle_missing_config()

        # Should exit with Docker configuration error
        mock_exit.assert_called_once()
        self.assertIn("Docker configuration error", mock_exit.call_args[0][0])

    @mock.patch("iSponsorBlockTV.utils.config.logger.info")
    def test_handle_missing_config_create_dir(self, mock_log):
        """Test _handle_missing_config creates directory when not in Docker."""
        # Create a config with a non-existent data_dir
        temp_dir = tempfile.TemporaryDirectory()
        nonexistent_dir = Path(temp_dir.name) / "nonexistent"

        config = Config(data_dir=nonexistent_dir)

        # Mock _is_docker to return False
        with mock.patch.object(Config, "_is_docker", return_value=False):
            # Mock Path.exists to return False
            with mock.patch.object(Path, "exists", return_value=False):
                # Mock save method to avoid actual file operations
                with mock.patch.object(Config, "save"):
                    config._handle_missing_config()

        # Should log the directory creation
        mock_log.assert_any_call("Creating data directory")

        # Clean up
        temp_dir.cleanup()

    def test_is_docker_method(self):
        """Test the _is_docker method."""
        # Mock os.getenv to return True
        with mock.patch("os.getenv", return_value="1"):
            self.assertTrue(Config._is_docker())

        # Mock os.getenv to return None
        with mock.patch("os.getenv", return_value=None):
            self.assertFalse(Config._is_docker())

    @mock.patch("iSponsorBlockTV.utils.config.sleep")
    @mock.patch("sys.exit")
    @mock.patch("iSponsorBlockTV.utils.config.logger.error")
    @mock.patch("iSponsorBlockTV.utils.config.logger.info")
    def test_exit_with_message(
        self, mock_log_info, mock_log_error, mock_exit, mock_sleep
    ):
        """Test the _exit_with_message method."""
        Config._exit_with_message("Test error message", 5)

        # Verify the error was logged
        mock_log_error.assert_called_once_with("Test error message")

        # Verify the exit message was logged
        mock_log_info.assert_called_once_with("Exiting in 5 seconds...")

        # Verify sleep was called
        mock_sleep.assert_called_once_with(5)

        # Verify exit was called
        mock_exit.assert_called_once_with(1)

    def test_equality_comparison(self):
        """Test the __eq__ method."""
        config1 = Config(
            data_dir=self.data_dir,
            devices=[Device(screen_id="test123")],
            apikey="testkey",
        )

        config2 = Config(
            data_dir=self.data_dir,
            devices=[Device(screen_id="test123")],
            apikey="testkey",
        )

        # Different config
        config3 = Config(
            data_dir=self.data_dir,
            devices=[Device(screen_id="different")],
            apikey="testkey",
        )

        # Should be equal (same data)
        self.assertEqual(config1, config2)

        # Should not be equal (different data)
        self.assertNotEqual(config1, config3)

        # Should not be equal to other types
        self.assertNotEqual(config1, "not a config")
