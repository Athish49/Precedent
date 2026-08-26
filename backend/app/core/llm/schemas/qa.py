from pydantic import BaseModel


class Citation(BaseModel):
    clause_ordinal: int
    excerpt: str


class QAAnswerOut(BaseModel):
    answer: str
    citations: list[Citation]
