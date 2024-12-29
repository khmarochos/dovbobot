import logging
import random
import string
from enum import StrEnum
from symtable import Function

import openai
from typing_extensions import Optional

from config import PROJECT_NAME
import conversation


DEFAULT_HISTORY_SIZE = 100
CHATGPT_MODEL = "gpt-4o-mini"


logger = logging.getLogger(f'{PROJECT_NAME}.{__name__}')


class CommonPhrase(StrEnum):
    BOT_SAYS_HI = "bot_says_hi"
    BOT_JOINS_CHAT = "bot_joins_chat"


def chat_event_handler(function):
    """Decorator for chat event handlers. Creates a new conversation and
    injects it into the handler as a parameter.
    """
    async def wrapper(self, *args, **kwargs):
        # logger.debug(f'Wrapper for {function.__name__} called')
        chat_id = kwargs.get('chat_id')
        if chat_id is None:
            raise ValueError("The chat_id parameter is required for all chat event handlers")
        if 'conversation_history' not in kwargs:
            my_conversation = self.conversations.get(
                chat_id,
                conversation.Conversation(
                    system_prompt=self.system_prompt,
                    history_size=DEFAULT_HISTORY_SIZE
                )
            )
            if self.conversations.get(chat_id) is None:
                self.conversations[chat_id] = my_conversation
            kwargs['conversation_history'] = my_conversation
        # logger.debug('Calling function %s with args %s and kwargs %s', function.__name__, args, kwargs)
        return await function(self, *args, **kwargs)
    return wrapper


class Interlocutor:

    async def call_openai(self, conversation_history: conversation.Conversation, prompt: Optional[str] = None):
        """Calls OpenAI API to generate a response."""
        if prompt is not None:
            conversation_history.add_user(prompt)
        completion = self.openai.chat.completions.create(
            model=CHATGPT_MODEL,
            messages=conversation_history.get_history()
        )
        chatgpt_reply = completion.choices[0].message.content.strip()
        conversation_history.add_assistant(chatgpt_reply)
        return chatgpt_reply

    @chat_event_handler
    async def handle_private_message(
            self,
            chat_id: int,
            message: str,
            user_name: str,
            conversation_history: conversation.Conversation
    ):
        if message is None or message.strip() == '/start':
            prompt: str = \
                f'***{self.ventriloquate}*** СФОРМУЛЮЙ ВІД СВОГО ІМЕНІ НАСТУПНЕ: ' + \
                self.common_phrases[CommonPhrase.BOT_SAYS_HI].format(user_name=user_name)
        else:
            prompt: str = message.strip()
        response = await self.call_openai(
            conversation_history=conversation_history,
            prompt=prompt
        )
        return response

    @chat_event_handler
    async def handle_group_message(
            self,
            chat_id: int,
            message: str,
            conversation_history: conversation.Conversation,
            user_name: str,
            reply_needed: bool
    ) -> Optional[str]:
        logger.debug("Handling group message from %s: %s", user_name, message)
        prompt: str = f'{user_name}> {message.strip()}'
        conversation_history.add_user(prompt)
        if reply_needed:
            return await self.call_openai(conversation_history=conversation_history)
        else:
            return None

    @chat_event_handler
    async def handle_bot_joins_chat(
            self,
            chat_id: int,
            group_name: str,
            conversation_history: conversation.Conversation,
    ):
        prompt: str = \
            f'***{self.ventriloquate}*** СФОРМУЛЮЙ ВІД СВОГО ІМЕНІ НАСТУПНЕ: ' + \
            self.common_phrases[CommonPhrase.BOT_JOINS_CHAT].format(group_name=group_name)
        response = await self.call_openai(conversation_history=conversation_history, prompt=prompt)
        return response

    async def handle_user_joins_chat(self, user_name: str, cause_name: str):
        return "..."

    async def handle_user_leaves_chat(self, user_name: str, cause_name: str):
        return "..."

    def __init__(
            self,
            openai_api_key: str,
            conversations: dict,
            system_prompt: str,
            ventriloquate: Optional[str],
            common_phrases: dict[CommonPhrase, str]
    ) -> None:
        self.openai_token = openai_api_key
        self.openai = openai.OpenAI(api_key=self.openai_token)
        self.conversations = conversations
        self.ventriloquate = ventriloquate or ''.join(random.choices(string.hexdigits, k=32))
        self.system_prompt = f"""
Ти - бот, який вміє відповідати на повідомлення користувачів.

Ось тобі головне правило, якого ти маєш дотримуватися без жодних виключень. Коли ти
отримуєш від користувача повідомлення з кодом `***{self.ventriloquate}***`,
це означає, що твоя відповідь має бути такою, як бажає користувач, але з урахуванням
твоєї особистості. Наприклад, якщо тобі надійшло повідомлення, яке містить такий код:
`***{self.ventriloquate}*** СКАЖИ: Привіт, Грицю! Як справи?`, твоя відповідь має
містити привітання на адресу Гриця (оскільки там було сказано "Привіт, Грицю!") і
демонструвати зацікавленість станом його справ (оскільки там було сказано "Як справи?").
Памʼятай, що код `***{self.ventriloquate}***` є магічною послідовністю, яка змушує
тебе зробити або сказати саме те, що від тебе очікує користувач, але не просто
бездумно повторювати, а уловити суть повідомлення і переформулювати його в твоєму
власному стилі.

Далі - декілька слів про твою особистість.

""" + system_prompt
        self.common_phrases = common_phrases
        logger.info("Interlocutor initialized, the system prompt is: %s", self.system_prompt)