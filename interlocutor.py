import json
import logging
import random
import string
import time
from enum import StrEnum
from symtable import Function

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
    Decorator for chat event handlers. Creates a new conversation and
    injects it into the handler as a parameter.

    :param function: The chat event handler function that needs to be wrapped
    :return: The wrapped function
    """
    async def wrapper(self, *args, **kwargs):
        # logger.debug(f'Wrapper for {function.__name__} called')
        chat_id = kwargs.get('chat_id')
        if chat_id is None:
            raise ValueError("The chat_id parameter is required for all chat event handlers")
        if 'conversation_history' not in kwargs:
            my_conversation = self.conversations.get(
                chat_id,
                conversation.Conversation(DEFAULT_HISTORY_SIZE)
            )
            if self.conversations.get(chat_id) is None:
                self.conversations[chat_id] = my_conversation
            kwargs['conversation_history'] = my_conversation
        return await function(self, *args, **kwargs)
    return wrapper


class Interlocutor:

    @staticmethod
    def generate_message(user_name: str, message: str) -> str:
        return json.dumps(
            {
                "type": "message",
                "content": {
                    "recipient": None,
                    "sender": user_name,
                    "message": message
                }
            }
        )

    @staticmethod
    def generate_prompt(prompt: str) -> str:
        return json.dumps(
            {
                "type": "prompt",
                "content": {
                    "recipient": PROJECT_NAME,
                    "sender": None,
                    "message": prompt
                }
            }
        )

    async def call_openai(
            self,
            prompt: Optional[str] = None
    ):
        logger.debug('Prompt: %s', prompt)
        request = self.openai.beta.threads.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=prompt
        )
        run = self.openai.beta.threads.runs.create(
            thread_id=self.thread.id,
            assistant_id=self.assistant_id,
        )
        while run.status == "queued" or run.status == "in_progress":
            logger.debug('Run status: %s', run.status)
            run = self.openai.beta.threads.runs.retrieve(
                thread_id=self.thread.id,
                run_id=run.id,
            )
            time.sleep(0.5)
        messages = self.openai.beta.threads.messages.list(
            thread_id=self.thread.id,
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
            message: str,
            user_name: str,
            conversation_history: conversation.Conversation
    ) -> list[str]:
        message = message.strip()
        logger.debug('PVT %s> %s', user_name, message)
        if message is None or message == '/start':
            what_to_say = self.common_phrases[CommonPhrase.BOT_SAYS_HI].format(user_name=user_name)
            responses = await self.call_openai(self.generate_prompt(what_to_say))
        else:
            responses = await self.call_openai(self.generate_message(user_name, message))
        logger.debug('PVT <%s %s', user_name, responses)
        return responses

    @chat_event_handler
    async def handle_group_message(
            self,
            chat_id: int,
            message: str,
            conversation_history: conversation.Conversation,
            user_name: str,
            group_name: str
    ) -> list[str]:
        message = message.strip()
        conversation_history.add_user(message)
        logger.debug('GRP %s, %s > %s', group_name, user_name, message)
        responses = await self.call_openai(self.generate_message(user_name, message))
        logger.debug('GRP %s, %s < %s', group_name, user_name, responses)
        return responses

    @chat_event_handler
    async def handle_bot_joins_chat(
            self,
            chat_id: int,
            group_name: str,
            conversation_history: conversation.Conversation,
    ) -> list[str]:
        what_to_say = self.common_phrases[CommonPhrase.BOT_JOINS_CHAT].format(group_name=group_name)
        responses = await self.call_openai(self.generate_prompt(what_to_say))
        return responses

    @chat_event_handler
    async def handle_user_joins_chat(
            self,
            chat_id: int,
            user_name: str,
            cause_name: str,
            invited: bool,
            conversation_history: conversation.Conversation
    ) -> list[str]:
        what_to_say = self.common_phrases[
            CommonPhrase.USER_INVITED_TO_CHAT if invited else CommonPhrase.USER_JOINS_CHAT
        ].format(
            user_name=user_name,
            inviter_name=cause_name
        )
        responses = await self.call_openai(self.generate_prompt(what_to_say))
        return responses

    @chat_event_handler
    async def handle_user_leaves_chat(
            self,
            chat_id: int,
            user_name: str,
            cause_name: str,
            kicked: bool,
            conversation_history: conversation.Conversation
    ) -> list[str]:
        what_to_say = self.common_phrases[
            CommonPhrase.USER_KICKED_FROM_CHAT if kicked else CommonPhrase.USER_LEAVES_CHAT
        ].format(
            user_name=user_name,
            kicker_name=cause_name
        )
        responses = await self.call_openai(self.generate_prompt(what_to_say))
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
        self.thread = self.openai.beta.threads.create()
