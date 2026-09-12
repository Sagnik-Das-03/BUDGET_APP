from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AskCorrection, ChatMessage, ChatThread
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
                     duration_sec: Optional[float] = None, query_json: Optional[str] = None) -> ChatMessage:
        message = ChatMessage(
            thread_id=thread_id, question=question, answer=answer,
            duration_sec=duration_sec, query_json=query_json,
        )
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

    def get_message(self, message_id: int) -> Optional[ChatMessage]:
        return self.session.get(ChatMessage, message_id)

    def set_feedback(self, message_id: int, helpful: bool, note: Optional[str] = None) -> Optional[ChatMessage]:
        message = self.get_message(message_id)
        if not message:
            return None
        message.feedback = "up" if helpful else "down"
        message.feedback_note = note
        self.session.flush()
        return message

    def add_correction(self, question: str, wrong_query_json: Optional[str], note: Optional[str]) -> AskCorrection:
        correction = AskCorrection(question=question, wrong_query_json=wrong_query_json, note=note)
        self.session.add(correction)
        self.session.flush()
        return correction

    def recent_corrections(self, limit: int = 5) -> list[AskCorrection]:
        stmt = select(AskCorrection).order_by(AskCorrection.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))
