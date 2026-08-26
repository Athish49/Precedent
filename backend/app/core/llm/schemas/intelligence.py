from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EasyPromptOut(BaseModel):
    structured_prompt: str
    route: Literal["s3", "s4"]
