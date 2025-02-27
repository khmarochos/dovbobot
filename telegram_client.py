# I agree, this is lame that I place some "business logic" to this module (like
# deciding what to do with the message). Perhaps I should move these parts to
# some separate module (like "brain.py" or kind of that). TODO: think about it.
import asyncio
import json
import logging
from asyncio import Task
from typing import Optional, Coroutine, Any

from telegram import Chat, ChatMember, ChatMemberUpdated, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ChatMemberHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from interlocutor import Interlocutor
from config import PROJECT_NAME

logger = logging.getLogger(f'{PROJECT_NAME}.{__name__}')


class TelegramClient:

    @staticmethod
    def extract_status_change(chat_member_update: ChatMemberUpdated) -> Optional[tuple[bool, bool]]:
        """Takes a ChatMemberUpdated instance and extracts whether the 'old_chat_member' was a member
        of the chat and whether the 'new_chat_member' is a member of the chat. Returns None, if
        the status didn't change.
        """
        status_change = chat_member_update.difference().get("status")
        old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

        if status_change is None:
            return None

        old_status, new_status = status_change
        was_member = old_status in [
            ChatMember.MEMBER,
            ChatMember.OWNER,
            ChatMember.ADMINISTRATOR,
        ] or (old_status == ChatMember.RESTRICTED and old_is_member is True)
        is_member = new_status in [
            ChatMember.MEMBER,
            ChatMember.OWNER,
            ChatMember.ADMINISTRATOR,
        ] or (new_status == ChatMember.RESTRICTED and new_is_member is True)

        return was_member, is_member

    @staticmethod
    async def process_responses(
            update: Update,
            responses: list,
            reply_to_message: Optional[int] = None
    ) -> None:
        for response in responses:
            response = json.loads(response)
            if response.get('type') == 'noop':
                continue
            message_parameters: dict = {
                'text': response.get('content', {}).get('message', 'Не знаю, що й сказати.'),
                'parse_mode': ParseMode.HTML
            }
            if reply_to_message is not None:
                message_parameters.update({'reply_to_message_id': reply_to_message})
            message_parameters.update({
                'text':
                    f'{message_parameters['text']}\n\n'
                    f'DEBUG INFO: <i>{response.get('content', {}).get('debug')}</i>'
            })
            await update.effective_chat.send_message(**message_parameters)

    async def track_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        chat_id = chat.id
        chat_type = chat.type
        chat_title = chat.title

        """Tracks the chats the bot is in."""
        if self.interlocutor.get_conversation(chat_id) is None:
            logger.info("Adding chat %s to the conversation tracker", chat_id)
            self.interlocutor.add_conversation(chat_id)

        result = self.extract_status_change(update.my_chat_member)
        if result is None:
            return
        was_member, is_member = result

        # Let's check who is responsible for the change
        cause_name = update.effective_user.full_name

        # Handle chat types differently:
        if chat_type == Chat.PRIVATE:
            if not was_member and is_member:
                logger.info("%s unblocked the bot", cause_name)
            elif was_member and not is_member:
                logger.info("%s blocked the bot", cause_name)
        elif chat_type in [Chat.GROUP, Chat.SUPERGROUP]:
            if not was_member and is_member:
                logger.info("%s added the bot to the group %s", cause_name, chat.title)
                hello: list = await self.interlocutor.handle_bot_joins_chat(
                    chat_id=chat_id,
                    group_name=chat_title
                )
                await self.process_responses(update, hello)
            elif was_member and not is_member:
                logger.info("%s removed the bot from the group %s", cause_name, chat.title)
        elif chat_type == Chat.CHANNEL:
            if not was_member and is_member:
                logger.info("%s added the bot to the channel %s", cause_name, chat.title)
            elif was_member and not is_member:
                logger.info("%s removed the bot from the channel %s", cause_name, chat.title)

    async def greet_chat_members(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Greets new users in chats and announces when someone leaves"""
        result = self.extract_status_change(update.chat_member)
        if result is None:
            return
        was_member, is_member = result

        cause_user = update.chat_member.from_user
        cause_user_id = cause_user.id
        cause_user_name = cause_user.mention_html()

        member_user = update.chat_member.new_chat_member.user
        member_user_id = member_user.id
        member_user_name = member_user.mention_html()

        task: Optional[Task[Any]] = None

        if not was_member and is_member:
            task = asyncio.create_task(
                self.interlocutor.handle_user_joins_chat(
                    chat_id=update.effective_chat.id,
                    user_name=member_user_name,
                    cause_name=cause_user_name,
                    invited=(cause_user_id != member_user_id)
                )
            )
        elif was_member and not is_member:
            task = asyncio.create_task(
                self.interlocutor.handle_user_leaves_chat(
                    chat_id=update.effective_chat.id,
                    user_name=member_user_name,
                    cause_name=cause_user_name,
                    kicked=(cause_user_id != member_user_id)
                )
            )

        if task is not None:
            task.add_done_callback(
                lambda future_result:
                    asyncio.create_task(
                        self.process_responses(
                            update,
                            future_result.result(),
                            reply_to_message=None
                        )
                    )
            )

    async def handle_chat_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.debug("Handling chat message")
        """Greets the user and records that they started a chat with the bot if it's a private chat.
        Since no `my_chat_member` update is issued when a user starts a private chat with the bot
        for the first time, we have to track it explicitly here.
        """
        user_name = update.effective_user.username or update.effective_user.full_name
        chat = update.effective_chat
        task: Optional[Task[Any]] = None
        reply_to_message = {}
        if chat.type == Chat.PRIVATE:
            task = asyncio.create_task(
                    self.interlocutor.handle_private_message(
                    chat_id=chat.id,
                    message=update.effective_message.text,
                    user_name=user_name
                )
            )
        elif chat.type in [Chat.GROUP, Chat.SUPERGROUP] and update.effective_message.text is not None:
            task = asyncio.create_task(
                self.interlocutor.handle_group_message(
                    chat_id=chat.id,
                    message=update.effective_message.text,
                    user_name=user_name,
                    group_name=chat.title,
                )
            )
            reply_to_message = {'reply_to_message': update.effective_message.message_id}

        if task is not None:
            task.add_done_callback(
                lambda future_result:
                    asyncio.create_task(
                        self.process_responses(
                            update,
                            future_result.result(),
                            **reply_to_message
                        )
                    )
            )

    def __init__(
            self,
            telegram_token: str,
            interlocutor: Interlocutor
    ) -> None:
        """Start the bot."""
        # Set the interlocutor
        self.interlocutor = interlocutor

        # Create the Application and pass it your bot's token.
        application = Application.builder().token(telegram_token).build()

        # Keep track of which chats the bot is in
        application.add_handler(ChatMemberHandler(self.track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
        # application.add_handler(CommandHandler("show_chats", self.show_chats))

        # Handle members joining/leaving chats.
        application.add_handler(ChatMemberHandler(self.greet_chat_members, ChatMemberHandler.CHAT_MEMBER))

        # Handle the messages
        application.add_handler(MessageHandler(filters.CHAT, self.handle_chat_message))

        # Run the bot until the user presses Ctrl-C
        # We pass 'allowed_updates' handle *all* updates including `chat_member` updates
        # To reset this, simply pass `allowed_updates=[]`
        application.run_polling(allowed_updates=Update.ALL_TYPES)
