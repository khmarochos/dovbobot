import asyncio.tasks
import json
import logging
import time
from enum import StrEnum
from threading import activeCount

from openai.pagination import SyncCursorPage
from openai.types.beta import Thread
from openai.types.beta.threads import Run

import openai
from typing_extensions import Optional

from config import PROJECT_NAME
import conversation


DEFAULT_HISTORY_SIZE = 100


logger = logging.getLogger(f'{PROJECT_NAME}.{__name__}')


class CommonPhrase(StrEnum):
    BOT_SAYS_HI = "bot_says_hi"
    BOT_JOINS_CHAT = "bot_joins_chat"
    USER_JOINS_CHAT = "user_joins_chat"
    USER_LEAVES_CHAT = "user_leaves_chat"
    USER_INVITED_TO_CHAT = "user_invited_to_chat"
    USER_KICKED_FROM_CHAT = "user_kicked_from_chat"


def chat_event_handler(function):
    """
    Decorator for chat event handlers.

    Finds or creates the related Conversation object and injects it into the
    wrapped function's kwargs. Conversation objects are needed to keep track of
    the chat history and, which is even more important, the related Thread
    object.

    A wrapped function MUST have the following parameters in its signature:
      - 'chat_id' (int): The chat ID (it's being used to find the related
        Conversation object),
      - 'conversation' (Conversation): The related Conversation object (it will
        be injected).

    A wrapped function MUST be called with at least one of the parameters
    listed above.

    :param function: The chat event handler function that needs to be wrapped
    :return: The wrapped function
    """
    async def wrapper(self, *args, **kwargs) -> asyncio.Task:
        # logger.debug(f'Wrapper for {function.__name__} called')
        # Is the 'conversation' parameter already provided?
        if kwargs.get('conversation') is None:
            # If the 'conversation' parameter is not provided, we'll attempt to
            # fetch the related Conversation object from the global dictionary
            # or create a new one if it doesn't exist.
            # Let's check if the 'chat_id' parameter is provided.
            if (chat_id := kwargs.get('chat_id')) is None:
                raise ValueError("The 'chat_id' parameter is required for all chat event handlers")
            # Try to find the related Conversation object or create a new one.
            if self.get_conversation(chat_id) is None:
                # Seems to be a new chat, let's create a new Conversation object.
                logger.debug(f'Creating a new conversation for chat {chat_id}')
                # Create a new thread.
                thread = self.create_thread()
                self.add_conversation(
                    chat_id=chat_id,
                    conversation=conversation.Conversation(
                        thread=thread,
                        history_size=DEFAULT_HISTORY_SIZE
                    )
                )
            kwargs['conversation'] = self.get_conversation(chat_id)
        return await function(self, *args, **kwargs)
    return wrapper

class Interlocutor:

    @staticmethod
    def generate_message(user_name: str, message: str, timestamp: int = None) -> str:
        if timestamp is None:
            timestamp = int(time.time())
        return json.dumps(
            {
                "type": "message",
                "content": {
                    "recipient": None,
                    "sender": user_name,
                    "message": message
                },
                "timestamp": timestamp
            }
        )

    @staticmethod
    def generate_prompt(prompt: str, timestamp: int = None) -> str:
        if timestamp is None:
            timestamp = int(time.time())
        return json.dumps(
            {
                "type": "prompt",
                "content": {
                    "recipient": PROJECT_NAME,
                    "sender": None,
                    "message": prompt
                },
                "timestamp": timestamp
            }
        )

    def add_conversation(self, chat_id: int, conversation: conversation.Conversation = None) -> None:
        self.conversations[chat_id] = conversation

    def remove_conversation(self, chat_id: int) -> None:
        self.conversations.pop(chat_id)

    def get_conversation(self, chat_id: int) -> conversation.Conversation:
        return self.conversations.get(chat_id)

    def reset_conversation(self, chat_id: int):
        conversation = self.get_conversation(chat_id)
        thread_id = conversation.get_thread_id()
        self.openai.beta.threads.delete(thread_id)
        conversation.set_thread(self.create_thread())

    def create_thread(self) -> Thread:
        return self.openai.beta.threads.create()

    async def call_openai(
            self,
            conversation: conversation.Conversation,
            prompt: Optional[str] = None
    ):
        logger.debug('Prompt: %s', prompt)
        while conversation.has_active_run():
            logger.debug('Waiting for the previous run to finish')
            await asyncio.sleep(0.5)
        request = self.openai.beta.threads.messages.create(
            thread_id=conversation.get_thread_id(),
            role="user",
            content=prompt
        )
        run = self.openai.beta.threads.runs.create(
            thread_id=conversation.get_thread_id(),
            assistant_id=self.assistant_id,
        )
        conversation.set_active_run(run)
        while run.status == "queued" or run.status == "in_progress":
            logger.debug('Run status: %s', run.status)
            run = self.openai.beta.threads.runs.retrieve(
                thread_id=conversation.get_thread_id(),
                run_id=run.id,
            )
            await asyncio.sleep(0.5)
        conversation.clear_active_run()
        messages = self.openai.beta.threads.messages.list(
            thread_id=conversation.get_thread_id(),
            run_id=run.id,
            after=request.id,
            order="asc",
        )
        responses = []
        for message in messages:
            if message.role == "assistant" and message.content is not None:
                for content_piece in message.content:
                    if content_piece.type == "text":
                        responses.append(content_piece.text.value)
        return responses

    @chat_event_handler
    async def handle_private_message(
            self,
            chat_id: int,
            conversation: conversation.Conversation,
            message: str,
            user_name: str
    ) -> list[str]:
        message = message.strip()
        conversation.add_user(message)
        logger.debug('PVT %s > %s', user_name, message)
        if message is None or message == '/start':
            what_to_say = self.common_phrases[CommonPhrase.BOT_SAYS_HI].format(user_name=user_name)
            responses = await self.call_openai(
                conversation=conversation,
                prompt=self.generate_prompt(what_to_say)
            )
        else:
            responses = await self.call_openai(
                conversation=conversation,
                prompt=self.generate_message(user_name, message)
            )
        logger.debug('PVT < %s %s', user_name, responses)
        return responses

    @chat_event_handler
    async def handle_group_message(
            self,
            chat_id: int,
            conversation: conversation.Conversation,
            message: str,
            user_name: str,
            group_name: str
    ) -> list[str]:
        message = message.strip()
        conversation.add_user(message)
        logger.debug('GRP %s, %s > %s', group_name, user_name, message)
        responses = await self.call_openai(
            conversation=conversation,
            prompt=self.generate_message(user_name, message)
        )
        logger.debug('GRP %s, %s < %s', group_name, user_name, responses)
        return responses

    @chat_event_handler
    async def handle_bot_joins_chat(
            self,
            chat_id: int,
            conversation: conversation.Conversation,
            group_name: str,
    ) -> list[str]:
        what_to_say = self.common_phrases[CommonPhrase.BOT_JOINS_CHAT].format(group_name=group_name)
        responses = await self.call_openai(
            conversation=conversation,
            prompt=self.generate_prompt(what_to_say)
        )
        return responses

    @chat_event_handler
    async def handle_user_joins_chat(
            self,
            chat_id: int,
            conversation: conversation.Conversation,
            user_name: str,
            cause_name: str,
            invited: bool,
    ) -> list[str]:
        what_to_say = self.common_phrases[
            CommonPhrase.USER_INVITED_TO_CHAT if invited else CommonPhrase.USER_JOINS_CHAT
        ].format(
            user_name=user_name,
            inviter_name=cause_name
        )
        responses = await self.call_openai(
            conversation=conversation,
            prompt=self.generate_prompt(what_to_say)
        )
        return responses

    @chat_event_handler
    async def handle_user_leaves_chat(
            self,
            chat_id: int,
            conversation: conversation.Conversation,
            user_name: str,
            cause_name: str,
            kicked: bool,
    ) -> list[str]:
        what_to_say = self.common_phrases[
            CommonPhrase.USER_KICKED_FROM_CHAT if kicked else CommonPhrase.USER_LEAVES_CHAT
        ].format(
            user_name=user_name,
            kicker_name=cause_name
        )
        responses = await self.call_openai(
            conversation=conversation,
            prompt=self.generate_prompt(what_to_say)
        )
        return responses

    def __init__(
            self,
            openai_api_key: str,
            assistant_id: str,
            conversations: dict,
            common_phrases: dict[CommonPhrase, str]
    ) -> None:
        self.openai_token = openai_api_key
        self.assistant_id = assistant_id
        self.common_phrases = common_phrases
        self.conversations = conversations
        # Initialize OpenAI objects
        self.openai = openai.OpenAI(api_key=self.openai_token)
        self.assistant = self.openai.beta.assistants.retrieve(assistant_id)
        self.thread = None