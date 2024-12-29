import logging
import argparse

import dynaconf


PROJECT_NAME = 'dovbobot'


logger = logging.getLogger(__name__)


class Configuration:

    def get_settings(self) -> dynaconf.Dynaconf:
        return self.settings

    def get_profile_name(self) -> str:
        return self.profile_name

    def __init__(self):

        argument_parser = argparse.ArgumentParser(description="The configuration profile")
        argument_parser.add_argument(
            "--profile",
            type=str,
            required=False,
            default="default",
            help="The configuration profile to use"
        )
        known_arguments, unknown_arguments = argument_parser.parse_known_args()
        self.profile_name = known_arguments.profile

        self.settings = dynaconf.Dynaconf(
            envvar_prefix="DOVBOBOT",
            settings_files=[f'etc/{self.profile_name}.yaml', f'etc/.{self.profile_name}.secrets.yaml'],
        )