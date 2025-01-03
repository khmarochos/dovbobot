import logging
from collections import deque
from enum import StrEnum

from config import PROJECT_NAME


logger = logging.getLogger(f'{PROJECT_NAME}.{__name__}')


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Conversation:

    def add(self, content, role):
        self.conversation_history.append({
            'content': content,
            'role': role
        })

    def add_system(self, content):
        self.add(content, MessageRole.SYSTEM.__str__())

    def add_user(self, content):
        self.add(content, MessageRole.USER.__str__())

    def add_assistant(self, content):
        self.add(content, MessageRole.ASSISTANT.__str__())

    def get_history(self) -> list:
        return [self.system_prompt] + list(self.conversation_history)

    def prettify(self):
        result = ''
        for message in self.get_history():
            result += f"{message['role'].capitalize()}: \n{message}\n\n"
        return result

    def __init__(
            self,
            system_prompt: str,
            history_size: int
    ) -> None:
        self.system_prompt = {'role': MessageRole.SYSTEM.__str__(), 'content': system_prompt}
        self.history_size = history_size
        self.conversation_history = deque(maxlen=history_size)
