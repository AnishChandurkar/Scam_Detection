"""FastAPI app — single POST /analyse endpoint.

Accepts the normalised input format defined in CLAUDE.md, runs all three checks
via the engine orchestrator, and returns the verdict in the output schema.

Start with:
    uvicorn engine.main:app --reload --port 8000
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from engine.utils.normaliser import normalize
import engine

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-22s  %(levelname)-5s  %(message)s",
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Finfluencer Scam Detection Engine",
    description=(
        "Platform-agnostic financial scam detection engine. "
        "Accepts normalised text content, runs NLP, SEBI registration, "
        "and market anomaly checks, and returns a weighted risk verdict."
    ),
    version="1.0.0",
)


# Request / Response models (mirrors CLAUDE.md schemas)

class InputMetadata(BaseModel):
    follower_count: int = 0
    post_url: str = ""


class AnalyseRequest(BaseModel):
    """Normalised input — matches the Input Format in CLAUDE.md."""
    text: str = Field(..., description="Full transcript or message text")
    platform: str = Field(
        ...,
        description="Source platform",
        examples=["telegram", "whatsapp", "youtube", "instagram", "facebook", "x"],
    )
    source_handle: str = Field(
        "",
        description="Channel name or username",
    )
    timestamp: Optional[str] = Field(
        None,
        description="ISO 8601 datetime; defaults to now if omitted",
    )
    metadata: InputMetadata = Field(
        default_factory=InputMetadata,
        description="Optional platform-specific metadata",
    )


class NlpSignal(BaseModel):
    scam_language_detected: bool
    flags: list[str]
    stock_mentioned: str


class SebiCheckSignal(BaseModel):
    registered: bool
    registration_number_present: bool


class MarketAnomalySignal(BaseModel):
    volume_zscore: float
    anomaly_detected: bool


class Signals(BaseModel):
    nlp: NlpSignal
    sebi_check: SebiCheckSignal
    market_anomaly: MarketAnomalySignal


class WeightBreakdown(BaseModel):
    nlp_weight: float
    sebi_weight: float
    market_weight: float
    final_score: float


class AnalyseResponse(BaseModel):
    """Verdict output — matches the Output Format in CLAUDE.md."""
    risk_score: Optional[float]
    verdict: str
    signals: Signals
    weight_breakdown: WeightBreakdown


# Endpoint

@app.post(
    "/analyse",
    response_model=AnalyseResponse,
    summary="Analyse content for financial scam signals",
    description=(
        "Accepts a normalised content object, runs NLP scam detection, "
        "SEBI registration verification, and market anomaly detection, "
        "then returns a weighted risk score and verdict."
    ),
)
async def analyse(req: AnalyseRequest):
    """Run the full detection pipeline on the submitted content."""
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="Field 'text' must not be empty.")

    # Map the public CLAUDE.md input schema to the internal normalizer format.
    item = normalize(
        text=req.text,
        platform=req.platform,
        author=req.source_handle,
        source=req.source_handle,
        timestamp=req.timestamp,
        url=req.metadata.post_url,
        extra={
            "follower_count": req.metadata.follower_count,
        },
    )

    logger.info(
        "POST /analyse  platform=%s  author=%s  text_len=%d",
        item["platform"], item["author"], len(item["text"]),
    )

    # Run the engine (all three checks + scoring).
    try:
        report = engine.analyze(item)
    except Exception as exc:
        logger.exception("Engine pipeline failed")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    # Return only the CLAUDE.md output fields.
    return AnalyseResponse(
        risk_score=report["risk_score"],
        verdict=report["verdict"],
        signals=report["signals"],
        weight_breakdown=report["weight_breakdown"],
    )


# Health check

@app.get("/health", include_in_schema=False)
async def health():
    """Liveness probe — always returns OK."""
    return {"status": "ok"}
