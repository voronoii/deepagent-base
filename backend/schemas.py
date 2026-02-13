"""Pydantic models for request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List


class ChatRequest(BaseModel):
    """Incoming chat request."""
    message: str = Field(..., description="User message")
    thread_id: str = Field(default="default", description="Conversation thread ID")


class ReasoningStepData(BaseModel):
    """SSE reasoning step event data."""
    name: str
    status: str  # "in_progress" | "completed"
    description: str = ""
    timestamp: str = ""


class DataCard(BaseModel):
    """Key-value data card for structured display."""
    label: str
    value: str


class MessageData(BaseModel):
    """SSE message event data."""
    role: str = "assistant"
    content: str
    title: str = ""
    dataCards: List[DataCard] = []
    source: str = ""
    processingTime: str = ""
