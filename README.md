# DovboBot

This project is a Telegeam bot that uses OpenAI for maintaining conversations.
The bot is able to participate in group chats, follow the conversation context,
and post comments when asked (it reacts to personal mentions and replies to its
messages). The bot is also able to reply to private messages and follow the
conversation context just like in group chats.

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/khmarochos/dovbobot.git
    cd dovbobot
    ```

2. Create a virtual environment and activate it:
    ```sh
    python3 -m venv venv
    source venv/bin/activate
    ```

3. Install the required dependencies:
    ```sh
    pip install -r requirements.txt
    ```

4. Configure the bot by editing the `etc/.default.secrets.yaml` file with your OpenAI API key and Telegram token:
    ```yaml
    openai:
      api_key: "your-openai-api-key"
    telegram:
      token: "your-telegram-bot-token"
    ```

## Usage

To start the bot, run the following command:
```sh
python main.py
```

## Configuration

The bot's behavior and responses can be configured in the `etc/default.yaml` file. You can adjust the logging level, system prompt, and common phrases used by the bot.

## Contributing

Contributions are welcome! Please fork the repository and create a pull request with your changes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for more details.

## Support

If you encounter any issues or have questions, please open an issue on GitHub.

## Donations

If the bot has helped you with a complex technical issue, consider making a donation to the "Democratic Axe" volunteer fund to support Ukrainian soldiers. [Donate here](https://jump.khmarochos.academy/sokyra).

```

This `README.md` file provides an overview of the project, installation instructions, usage details, configuration options, contribution guidelines, license information, and a donation link.