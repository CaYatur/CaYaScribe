from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Quality = Literal["fast", "balanced", "high", "max"]
Enhance = Literal["off", "auto", "on"]


class JobCreate(BaseModel):
    mediaPath: str
    language: str = "auto"
    quality: Quality = "balanced"
    speakerCount: int | None = Field(default=None, ge=1, le=32)
    enhance: Enhance = "auto"


class Segment(BaseModel):
    id: str
    speakerId: str
    startMs: int
    endMs: int
    text: str


class Speaker(BaseModel):
    id: str
    name: str


class JobResult(BaseModel):
    jobId: str
    language: str
    engine: str
    diarization: str
    segments: list[Segment]
    speakers: list[Speaker]
