"""The agent's output, shaped like the API's Report (contracts/openapi.yaml#/components/schemas/Report)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from inland_worker.contracts.models import Evidence

SectionKey = Literal[
    "short_answer",
    "observed",
    "calculated",
    "official",
    "agreement",
    "limitations",
    "layers_and_charts",
    "sources",
]
TITLES = {
    "short_answer": "Short answer",
    "observed": "What was observed",
    "calculated": "What was calculated",
    "official": "What official sources report",
    "agreement": "Agreement and disagreement",
    "limitations": "Uncertainty and limitations",
    "sources": "Sources",
}


class ReportSection(BaseModel):
    key: SectionKey
    title: str
    markdown: str
    evidence_ids: list[str] = Field(default_factory=list)


class Source(BaseModel):
    source: str
    source_url: str


class Report(BaseModel):
    job_id: str
    confidence: Literal[
        "unverified_detection", "corroborated_signal", "officially_reported", "insufficient_evidence"
    ]
    sections: list[ReportSection]
    limitations: list[str]
    sources: list[Source]
    pdf_url: str | None = None
    generated_at: datetime

    def markdown(self) -> str:
        label = self.confidence.replace("_", " ").capitalize()
        out = [f"**Confidence: {label}**", ""]
        for s in self.sections:
            out += [f"### {s.title}", s.markdown, ""]
        return "\n".join(out)


class AnalysisResult(BaseModel):
    """What run_analysis returns: the report, every evidence item it cites, and a trace of what happened."""

    declined: bool = False
    decline_code: str | None = None
    message: str | None = None
    report: Report | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    plan: list[dict[str, Any]] = Field(default_factory=list)
    plan_source: Literal["llm", "fallback", "none"] = "none"
    explanation_source: Literal["llm", "template", "none"] = "none"
    models_used: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
