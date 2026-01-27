from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    """引用来源信息。"""
    source_id: str = Field(..., description="Stable source identifier for a chunk.")
    title: str = Field(..., description="Filename or document title.")
    snippet: str = Field(..., description="Short preview of the chunk.")
    source_type: str = Field(..., description="Where the source comes from.")
    path: str = Field(..., description="Filesystem path to the source.")


class Claim(BaseModel):
    """结论与对应引用。"""
    text: str = Field(..., description="Claim grounded in provided evidence.")
    source_ids: List[str] = Field(..., description="List of source_id values backing the claim.")

    @field_validator("source_ids")
    @classmethod
    def source_ids_not_empty(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("source_ids must not be empty")
        return value


class Report(BaseModel):
    """结构化报告输出。"""
    summary: str = Field(..., description="Short summary for the answer.")
    claims: List[Claim] = Field(..., description="List of grounded claims.")
    sources: List[Source] = Field(..., description="Sources used as evidence.")

    @field_validator("claims")
    @classmethod
    def claims_not_empty(cls, value: List[Claim]) -> List[Claim]:
        if not value:
            raise ValueError("claims must not be empty")
        return value

    def validate_source_ids(self) -> None:
        allowed = {source.source_id for source in self.sources}
        for claim in self.claims:
            invalid = [source_id for source_id in claim.source_ids if source_id not in allowed]
            if invalid:
                raise ValueError(
                    "claim has source_ids not present in sources: " + ", ".join(invalid)
                )
