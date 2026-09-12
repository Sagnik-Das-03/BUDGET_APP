from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatThread
from app.utils import utcnow


class ChatRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_threads(self) -> list[ChatThread]:
        stmt = select(ChatThread).order_by(ChatThread.updated_at.desc())
        return list(self.session.scalars(stmt))

    def get_thread(self, thread_id: int) -> Optional[ChatThread]:
        return self.session.get(ChatThread, thread_id)

    def create_thread(self, title: str = "New chat") -> ChatThread:
        thread = ChatThread(title=title)
        self.session.add(thread)
        self.session.flush()
        return thread

    def delete_thread(self, thread_id: int) -> bool:
        thread = self.get_thread(thread_id)
        if not thread:
            return False
        self.session.delete(thread)
        self.session.flush()
        return True

    def list_messages(self, thread_id: int) -> list[ChatMessage]:
        stmt = select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.id)
        return list(self.session.scalars(stmt))

    def add_message(self, thread_id: int, question: str, answer: str,
                     duration_sec: Optional[float] = None) -> ChatMessage:
        message = ChatMessage(thread_id=thread_id, question=question, answer=answer, duration_sec=duration_sec)
        self.session.add(message)
        thread = self.get_thread(thread_id)
        if thread:
            thread.updated_at = utcnow()
            # First exchange in a thread names it, so tabs are recognizable at a
            # glance instead of every tab reading "New chat".
            if thread.title == "New chat":
                thread.title = question[:60]
        self.session.flush()
        return message
