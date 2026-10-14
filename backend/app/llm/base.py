from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


class LLMClient(Protocol):
    async def chat(self, messages: list[Message]) -> str: ...
