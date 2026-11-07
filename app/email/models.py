from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class IncomingEmail:
    message_id: str
    from_email: str
    subject: str = ""
    body: str = ""
    from_name: str = ""
    reply_to: list[str] = field(default_factory=list)
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    return_path: str = ""
    conversation_id: str = ""
    graph_id: str = ""
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    headers: dict[str, str] = field(default_factory=dict)  # chaves em minúsculas

    def __post_init__(self) -> None:
        self.message_id = self.message_id.strip()
        self.from_email = (self.from_email or "").strip().lower()
        self.reply_to = [a.strip().lower() for a in self.reply_to if a and a.strip()]
        self.cc = [a.strip().lower() for a in self.cc if a and a.strip()]
        self.headers = {k.lower(): v for k, v in self.headers.items()}
        if not self.conversation_id:
            self.conversation_id = self.message_id
