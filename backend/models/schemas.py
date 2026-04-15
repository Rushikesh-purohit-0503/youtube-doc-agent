from pydantic import BaseModel, HttpUrl
from typing import Optional


class GenerateRequest(BaseModel):
    youtube_url: HttpUrl


class GenerateResponse(BaseModel):
    job_id: str
    status: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str


class HistoryItem(BaseModel):
    id: str
    job_id: str
    title: str
    thumbnail_url: str
    created_at: str
