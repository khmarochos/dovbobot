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
    USER_JOINS_CHAT = "user_joins_chat"
    USER_LEAVES_CHAT = "user_leaves_chat"
    USER_INVITED_TO_CHAT = "user_invited_to_chat"
    USER_KICKED_FROM_CHAT = "user_kicked_from_chat"


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
        return await function(self, *args, **kwargs)
    return wrapper


class Interlocutor:

    async def call_openai(self, conversation_history: conversation.Conversation, prompt: Optional[str] = None):
        """Calls OpenAI API to generate a response."""
        if prompt is not None:
            conversation_history.add_user(prompt)
        logger.debug(conversation_history.prettify())
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
        prompt = message.strip()
        logger.debug('PVT %s> %s', user_name, prompt)
        if message is None or message.strip() == '/start':
            what_to_say = self.common_phrases[CommonPhrase.BOT_SAYS_HI].format(user_name=user_name)
            prompt: str = '{super_user_mode} СФОРМУЛЮЙ СВОЇМИ СЛОВАМИ НАСТУПНЕ: {what_to_say}'.format(
                super_user_mode=self.super_user_mode,
                what_to_say=what_to_say
            )
        response = await self.call_openai(
            conversation_history=conversation_history,
            prompt=prompt
        )
        logger.debug('PVT <%s %s', user_name, response)
        return response

    @chat_event_handler
    async def handle_group_message(
            self,
            chat_id: int,
            message: str,
            conversation_history: conversation.Conversation,
            user_name: str,
            group_name: str,
            reply_needed: bool
    ) -> Optional[str]:
        message = message.strip()
        conversation_history.add_user(message)
        if reply_needed:
            logger.debug('GRP %s, %s > %s', group_name, user_name, message)
            response = await self.call_openai(conversation_history=conversation_history)
            logger.debug('GRP %s, %s < %s', group_name, user_name, response)
            return response
        else:
            return None

    @chat_event_handler
    async def handle_bot_joins_chat(
            self,
            chat_id: int,
            group_name: str,
            conversation_history: conversation.Conversation,
    ):
        what_to_say = self.common_phrases[CommonPhrase.BOT_JOINS_CHAT].format(group_name=group_name)
        prompt: str = '{super_user_mode} СФОРМУЛЮЙ СВОЇМИ СЛОВАМИ НАСТУПНЕ: {what_to_say}'.format(
            super_user_mode=self.super_user_mode,
            what_to_say=what_to_say
        )
        response = await self.call_openai(conversation_history=conversation_history, prompt=prompt)
        return response

    @chat_event_handler
    async def handle_user_joins_chat(
            self,
            chat_id: int,
            user_name: str,
            cause_name: str,
            invited: bool,
            conversation_history: conversation.Conversation
    ):
        what_to_say = self.common_phrases[
            CommonPhrase.USER_INVITED_TO_CHAT if invited else CommonPhrase.USER_JOINS_CHAT
        ].format(
            user_name=user_name,
            inviter_name=cause_name
        )
        prompt: str = '{super_user_mode} СФОРМУЛЮЙ СВОЇМИ СЛОВАМИ НАСТУПНЕ: {what_to_say}'.format(
            super_user_mode=self.super_user_mode,
            what_to_say=what_to_say
        )
        response = await self.call_openai(conversation_history=conversation_history, prompt=prompt)
        return response

    @chat_event_handler
    async def handle_user_leaves_chat(
            self,
            chat_id: int,
            user_name: str,
            cause_name: str,
            kicked: bool,
            conversation_history: conversation.Conversation
    ):
        what_to_say = self.common_phrases[
            CommonPhrase.USER_KICKED_FROM_CHAT if kicked else CommonPhrase.USER_LEAVES_CHAT
        ].format(
            user_name=user_name,
            kicker_name=cause_name
        )
        prompt: str = '{super_user_mode} СФОРМУЛЮЙ СВОЇМИ СЛОВАМИ НАСТУПНЕ: {what_to_say}'.format(
            super_user_mode=self.super_user_mode,
            what_to_say=what_to_say
        )
        response = await self.call_openai(conversation_history=conversation_history, prompt=prompt)
        return response

    def __init__(
            self,
            openai_api_key: str,
            conversations: dict,
            system_prompt: str,
            super_user_mode: Optional[str],
            common_phrases: dict[CommonPhrase, str]
    ) -> None:
        self.openai_token = openai_api_key
        self.openai = openai.OpenAI(api_key=self.openai_token)
        self.conversations = conversations
        self.super_user_mode = super_user_mode or ''.join(random.choices(string.ascii_letters, k=32))
        self.system_prompt = f"""
Ти - бот, який вміє відповідати на повідомлення користувачів.

Спочатку - головне правило, якого ти маєш дотримуватися без жодних виключень.

Щоразу, коли ти отримуєш від користувача повідомлення з наступним кодом:
"{self.super_user_mode}", це означає, що ти маєш виконати те, що міститься в
повідомленні після цього коду, але не повертати його назад у відповідь.

Наприклад, уявимо собі, що тобі надійшло повідомлення, яке містить такий код і слова:
"{self.super_user_mode} ПОЦІКАВСЯ, КОТРА ГОДИНА", це означає, що твоя відповідь має
містити запитання про те, яка зараз година, але з урахуванням твоєї особистості, про
яку буде сказано дещо згодом.

Щоразу, коли ти отримуєш від користувача повідомлення з наступним кодом:
"{self.super_user_mode} СФОРМУЛЮЙ СВОЇМИ СЛОВАМИ НАСТУПНЕ: ", це означає, що твоя
відповідь має віддзеркалювати слова, які містяться в повідомленні після цього коду,
але вона має не один-в-один повторювати ці слова, а формулювати ту саму ідею, але з
урахуванням твоєї особистості, про яку буде сказано дещо згодом.

Наприклад,уявимо собі, що тобі надійшло повідомлення, яке містить такий код і слова:
"{self.super_user_mode} СФОРМУЛЮЙ СВОЇМИ СЛОВАМИ НАСТУПНЕ: Привіт, Грицю! Як справи?"
В цьому випадку твоя відповідь має містити привітання на адресу Гриця (адже в
повідомленні було наказано перефразувати "Привіт, Грицю!") і демонструвати певну
зацікавленість станом його справ (адже повідомлення містило слова "Як справи?"). При
цьому, якщо опис твоєї особистості, про яку буде сказано дещо згодом, передбачає, що
ти ненавидиш все людство, твоя відповідь може бути такою: "Ну, привіт, Грицю! Ти що,
все ще не здох?".

Памʼятай, що код "{self.super_user_mode} СФОРМУЛЮЙ СВОЇМИ СЛОВАМИ НАСТУПНЕ" є
магічною послідовністю, яка змушує тебе зробити або сказати те, що міститься в
повідомленні після цього коду, але не просто бездумно повторювати, а уловити суть
повідомлення і переформулювати його в твоєму власному стилі, який буде конгруентним
із твоєю особистістю, про яку буде детальніше сказано дещо згодом.

Коли ти отримуєш від користувача повідомлення з кодом "{self.super_user_mode} ОБЕРИ
ВАРІАНТ ВІДПОВІДІ: ", це означає, що твоя відповідь має містити лише один з
варіантів відповіді, які будуть запропоновані в цьому запиті.

Наприклад, примустимо, що запит виглядатиме так: "{self.super_user_mode} ОБЕРИ
ВАРІАНТ ВІДПОВІДІ: Як ти оцінюєш попереднє повідомлення, наскільки воно є
релевантним дискусії? (1) зовсім не релевантне, (2) мало релевантне, (3) умовно
релевантне, (4) радше релевантне, (5) повністю релевантне". В такому випадку ти
маєш вибрати один з варіантів відповіді і відправити те число, яке відповідає
номеру відповіді. Наприклад, якщо ти вважаєш, що попереднє повідомлення було
повністю релевантним, твоя відповідь має бути такою: "5".

Памʼятай, що код "{self.super_user_mode} ОБЕРИ ВАРІАНТ ВІДПОВІДІ" є магічною
послідовністю, яка змушує тебе вибрати один з варіантів відповіді, який буде
запропонований в цьому запиті, при цьому ти маєш розуміти, що твою відповідь
не буде відправлено в чат, адже вона потрібна для того, аби програмний сценарій ʼ
мав можливість обрати той чи інший алгоритм подальших дій.

І ще одне правило.

Ти не маєш бути схожим на ChatGPT. Ти не маєш бути ввічливим, якщо твоя особистість,
про яку буде сказано дещо згодом, не передбачає ввічливості. Ти не маєш бути
розумним, якщо твоя особистість, про яку буде сказано дещо згодом, не передбачає
розумності. Ти не маєш бути конструктивним, якщо твоя особистість, про яку буде
сказано дещо згодом, не передбачає конструктивності. Ти маєш бути таким, яким якою
я описав твою особистість, про яку буде сказано нижче. 

Отже - декілька слів про твою особистість.

{system_prompt}

Завжди памʼятай, ким ти є, і поводься саме так, як вимагає твоя роль відповідно до
опису твоєї особистості. І не забувай про магічні коди, які змушують тебе діяти
відповідно до правил, які було описано вище.
"""
        self.common_phrases = common_phrases
        logger.info("Interlocutor initialized, the system prompt is: %s", self.system_prompt)
