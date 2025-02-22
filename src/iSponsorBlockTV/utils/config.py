import json
import os
import sys
import time

from iSponsorBlockTV.constants import config_file_blacklist_keys


class Device:
    def __init__(self, args_dict):
        self.screen_id = ""
        self.offset = 0
        self.__load(args_dict)
        self.__validate()

    def __load(self, args_dict):
        for i in args_dict:
            setattr(self, i, args_dict[i])
        # Change offset to seconds (from milliseconds)
        self.offset = self.offset / 1000

    def __validate(self):
        if not self.screen_id:
            raise ValueError("No screen id found")


class Config:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.config_file = data_dir + "/config.json"

        self.devices = []
        self.apikey = ""
        self.skip_categories = []  # These are the categories on the config file
        self.skip_count_tracking = True
        self.mute_ads = False
        self.skip_ads = False
        self.auto_play = True
        self.join_name = "iSponsorBlockTV"
        self.__load()

    def validate(self):
        if hasattr(self, "atvs"):
            print(
                (
                    "The atvs config option is deprecated and has stopped working."
                    " Please read this for more information on upgrading to V2:"
                    " \nhttps://github.com/dmunozv04/iSponsorBlockTV/wiki/Migrate-from-V1-to-V2"
                ),
            )
            print("Exiting in 10 seconds...")
            time.sleep(10)
            sys.exit()
        if not self.devices:
            print("No devices found, please add at least one device")
            print("Exiting in 10 seconds...")
            time.sleep(10)
            sys.exit()
        self.devices = [Device(i) for i in self.devices]
        if not self.skip_categories:
            self.skip_categories = ["sponsor"]
            print("No categories found, using default: sponsor")

    def __load(self):
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                for i in config:
                    if i not in config_file_blacklist_keys:
                        setattr(self, i, config[i])
        except FileNotFoundError:
            print("Could not load config file")
            # Create data directory if it doesn't exist (if we're not running in docker)
            if not os.path.exists(self.data_dir):
                if not os.getenv("iSPBTV_docker"):
                    print("Creating data directory")
                    os.makedirs(self.data_dir)
                else:  # Running in docker without mounting the data dir
                    print(
                        "Running in docker without mounting the data dir, check the"
                        " wiki for more information: "
                        "https://github.com/dmunozv04/iSponsorBlockTV/wiki/Installation#Docker"
                    )
                    print(
                        ("This image has been updated to v2, and requires changes."),
                        ("Please read this for more information on upgrading to V2:"),
                        "https://github.com/dmunozv04/iSponsorBlockTV/wiki/Migrate-from-V1-to-V2",
                    )
                    print("Exiting in 10 seconds...")
                    time.sleep(10)
                    sys.exit()
            else:
                print("Blank config file created")

    def save(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            config_dict = self.__dict__
            # Don't save the config file name
            config_file = self.config_file
            data_dir = self.data_dir
            del config_dict["config_file"]
            del config_dict["data_dir"]
            json.dump(config_dict, f, indent=4)
            self.config_file = config_file
            self.data_dir = data_dir

    def __eq__(self, other):
        if isinstance(other, Config):
            return self.__dict__ == other.__dict__
        return False
