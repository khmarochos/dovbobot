import logging
from collections import deque
from enum import StrEnum

from openai.types.beta import Thread

from openai import OpenAI

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

    def set_active_run(self, run):
        self.active_run = run

    def get_active_run(self):
        return self.active_run

    def has_active_run(self):
        return self.active_run is not None

    def clear_active_run(self):
        self.set_active_run(None)

    def get_history(self) -> list:
        return list(self.conversation_history)

    def get_thread(self) -> Thread:
        return self.thread

    def get_thread_id(self) -> str:
        return self.get_thread().id

    def prettify(self):
        result = ''
        for message in self.get_history():
            result += f"{message['role'].capitalize()}: \n{message}\n\n"
        return result

    def __init__(
            self,
            thread: Thread,
            history_size: int
    ) -> None:
        self.thread = thread
        self.history_size = history_size
        self.conversation_history = deque(maxlen=history_size)
        self.active_run = None
