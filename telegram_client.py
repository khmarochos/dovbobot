import logging
from typing import Optional, Coroutine, Any

from telegram import Chat, ChatMember, ChatMemberUpdated, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
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


    async def track_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Tracks the chats the bot is in."""
        result = self.extract_status_change(update.my_chat_member)
        if result is None:
            return
        was_member, is_member = result

        # Let's check who is responsible for the change
        cause_name = update.effective_user.full_name

        # Handle chat types differently:
        chat = update.effective_chat
        if chat.type == Chat.PRIVATE:
            if not was_member and is_member:
                # This may not be really needed in practice because most clients will automatically
                # send a /start command after the user unblocks the bot, and start_private_chat()
                # will add the user to "user_ids".
                # We're including this here for the sake of the example.
                logger.info("%s unblocked the bot", cause_name)
                context.bot_data.setdefault("user_ids", set()).add(chat.id)
            elif was_member and not is_member:
                logger.info("%s blocked the bot", cause_name)
                context.bot_data.setdefault("user_ids", set()).discard(chat.id)
        elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
            if not was_member and is_member:
                logger.info("%s added the bot to the group %s", cause_name, chat.title)
                context.bot_data.setdefault("group_ids", set()).add(chat.id)
                hello: str = await self.interlocutor.handle_bot_joins_chat(chat_id=chat.id, group_name=chat.title)
                await update.effective_chat.send_message(hello, parse_mode=ParseMode.HTML)
            elif was_member and not is_member:
                logger.info("%s removed the bot from the group %s", cause_name, chat.title)
                context.bot_data.setdefault("group_ids", set()).discard(chat.id)
        elif chat.type == Chat.CHANNEL:
            if not was_member and is_member:
                logger.info("%s added the bot to the channel %s", cause_name, chat.title)
                context.bot_data.setdefault("channel_ids", set()).add(chat.id)
            elif was_member and not is_member:
                logger.info("%s removed the bot from the channel %s", cause_name, chat.title)
                context.bot_data.setdefault("channel_ids", set()).discard(chat.id)


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

        message_text = f'Салют, {member_user_name}!'

        if not was_member and is_member:
            if cause_user_id == member_user_id:
                message_text = f"{member_user_name} приєднався до чату. Ласкаво просимо!"
            else:
                message_text = f"{member_user_name} приєднався до чату завдяки {cause_user_name}. Ласкаво просимо!"
        elif was_member and not is_member:
            if cause_user_id == member_user_id:
                message_text = f"{member_user_name} більше не з нами."
            else:
                message_text = f"{member_user_name} більше не з нами. Дякуємо за це {cause_user_name}."

        await update.effective_chat.send_message(message_text, parse_mode=ParseMode.HTML)


    async def handle_chat_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Greets the user and records that they started a chat with the bot if it's a private chat.
        Since no `my_chat_member` update is issued when a user starts a private chat with the bot
        for the first time, we have to track it explicitly here.
        """
        user_name = update.effective_user.full_name
        chat = update.effective_chat
        if chat.type == Chat.PRIVATE:
            if chat.id not in context.bot_data.get("user_ids", set()):
                logger.info("%s started a private chat with the bot", user_name)
                context.bot_data.setdefault("user_ids", set()).add(chat.id)
            response = await self.interlocutor.handle_private_message(
                chat_id=chat.id,
                message=update.effective_message.text,
                user_name=user_name
            )
            await update.effective_message.reply_markdown(response)
        elif chat.type in [Chat.GROUP, Chat.SUPERGROUP] and update.effective_message.text is not None:
            must_reply = (
                (
                    # Check if the message contains the bot's username
                    update.effective_message.text.__contains__('@dovbobot')
                ) or
                (
                    # Check if the message is a reply to the bot's message
                    update.effective_message.reply_to_message is not None and
                    update.effective_message.reply_to_message.from_user is not None and
                    update.effective_message.reply_to_message.from_user.id == context.bot.id
                )
            )
            response = await self.interlocutor.handle_group_message(
                chat_id=chat.id,
                message=update.effective_message.text,
                user_name=user_name,
                reply_needed=must_reply
            )
            if must_reply:
                await update.effective_message.reply_markdown(response)

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

        # Interpret any other command or text message as a start of a private chat.
        # This will record the user as being in a private chat with bot.
        application.add_handler(MessageHandler(filters.CHAT, self.handle_chat_message))

        # Run the bot until the user presses Ctrl-C
        # We pass 'allowed_updates' handle *all* updates including `chat_member` updates
        # To reset this, simply pass `allowed_updates=[]`
        application.run_polling(allowed_updates=Update.ALL_TYPES)
