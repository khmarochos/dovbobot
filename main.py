#!/usr/bin/env python

import logging

import config
import interlocutor
import telegram_client


def setup_logging(logging_level: int, logging_format: str) -> None:

    class ModuleFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return (record.levelno >= logging.WARNING) or (record.name.startswith(f'{config.PROJECT_NAME}'))

    logger = logging.getLogger()
    logger.setLevel(logging_level)

    handler = logging.StreamHandler()
    handler.setLevel(logging_level)
    handler.setFormatter(logging.Formatter(logging_format))

    handler.addFilter(ModuleFilter())
    logger.addHandler(handler)

def main() -> None:

    configuration = config.Configuration()
    configuration_settings = configuration.get_settings()
    configuration_profile = configuration.get_profile_name()

    setup_logging(
        logging_level=configuration_settings.logging.level,
        logging_format=configuration_settings.logging.format
    )
    logger = logging.getLogger(f'{config.PROJECT_NAME}.{__name__}')

    logger.debug(f"Chosen profile: {configuration_profile}")
    logger.debug(f"Loaded settings: {configuration_settings}")

    my_conversations = {}

    my_interlocutor = interlocutor.Interlocutor(
        openai_api_key=configuration_settings.openai.api_key,
        conversations=my_conversations,
        ventriloquate=None,
        system_prompt=configuration_settings.interlocutor.system_prompt,
        common_phrases=configuration_settings.interlocutor.common_phrases
    )

    my_telegram_client = telegram_client.TelegramClient(
        telegram_token=configuration_settings.telegram.token,
        interlocutor=my_interlocutor,
    )

if __name__ == "__main__":
    main()
