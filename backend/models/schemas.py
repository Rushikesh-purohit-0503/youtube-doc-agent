from typing import Literal, Optional

from pydantic import BaseModel, HttpUrl

TEMPLATES = Literal['storybook', 'professional', 'academic', 'minimal']


class GenerateRequest(BaseModel):
    youtube_url: HttpUrl
    template: TEMPLATES = 'storybook'


class GenerateResponse(BaseModel):
    job_id: str
    status: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None


class HistoryItem(BaseModel):
    id: str
    job_id: str
    title: str
    thumbnail_url: str
    created_at: str
