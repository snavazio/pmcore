"""
PMCore REST API
===============
FastAPI server exposing the PMCore pipeline over HTTP.

Endpoints:
  POST /plan         — Full pipeline (Planner + Reasoner + Communicator)
  POST /plan/quick   — Planner + Reasoner only (no comms)
  GET  /health       — Service health check
  GET  /models       — Loaded model info

Usage:
  uv run python api.py

Then call from WordPress plugin, EVO-X2, or anywhere on Tailscale:
  curl -X POST http://100.79.35.85:8765/plan \
    -H "Content-Type: application/json" \
    -d '{"request": "Plan a hotel lobby renovation with a 8-week deadline."}'
"""

import os
import time
import json
import torch
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
from contextlib import asynccontextmanager

from pmcore.inference import PMCorePipeline, GenerationConfig

# ── App State ─────────────────────────────────────────────────────────────────

pipeline: Optional[PMCorePipeline] = None
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all models on startup."""
    global pipeline
    print("\nPMCore API starting up...")
    print("Loading all three models into VRAM...")
    pipeline = PMCorePipeline(device="cuda", preload=True)
    print("PMCore API ready.\n")
    yield
    print("PMCore API shutting down.")


app = FastAPI(
    title="PMCore API",
    description="Purpose-built AI Project Management reasoning engine",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow all origins (Tailscale LAN + WordPress)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ─────────────────────────────────────────────────

class PlanRequest(BaseModel):
    request: str = Field(
        ...,
        description="The PM request to process",
        example="Plan a hotel lobby renovation. Budget $2M, 8-week deadline, 5-person team."
    )
    comm_request: str = Field(
        default="Write a professional project kickoff summary for stakeholders.",
        description="What type of communication to generate"
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens:  int   = Field(default=512, ge=64, le=1024)
    verbose:     bool  = Field(default=False)


class QuickPlanRequest(BaseModel):
    request: str = Field(..., description="The PM request to process")
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)


class TaskGraphResponse(BaseModel):
    tasks:        Optional[dict]
    num_tasks:    int
    methodology:  str
    duration_days: int
    raw_output:   str


class RiskResponse(BaseModel):
    risk_analysis:  Optional[dict]
    overall_health: str
    top_risks:      list
    critical_path:  list
    raw_output:     str


class CommunicationResponse(BaseModel):
    communication: str
    comm_type:     str


class PlanResponse(BaseModel):
    request:       str
    planner:       TaskGraphResponse
    reasoner:      RiskResponse
    communicator:  CommunicationResponse
    latency_ms:    dict
    total_ms:      float
    model_version: str = "PMCore v1.0"


class QuickPlanResponse(BaseModel):
    request:    str
    planner:    TaskGraphResponse
    reasoner:   RiskResponse
    latency_ms: dict
    total_ms:   float


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Service health check."""
    uptime = round(time.time() - start_time)
    gpu_info = {}
    if torch.cuda.is_available():
        gpu_info = {
            "name":        torch.cuda.get_device_name(0),
            "vram_total":  f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB",
            "vram_used":   f"{torch.cuda.memory_allocated(0) / 1e9:.1f}GB",
            "vram_free":   f"{(torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)) / 1e9:.1f}GB",
        }
    return {
        "status":   "healthy",
        "uptime_s": uptime,
        "models_loaded": pipeline is not None,
        "gpu": gpu_info,
        "version": "PMCore v1.0",
    }


@app.get("/models")
async def models_info():
    """Return info about loaded models."""
    if pipeline is None:
        raise HTTPException(503, "Models not loaded yet")

    info = {}
    for comp, model in pipeline.loader._models.items():
        info[comp] = {
            "params_m": round(model.count_params() / 1e6, 1),
            "layers":   model.config.num_layers,
            "hidden":   model.config.hidden_size,
            "heads":    f"{model.config.num_heads}/{model.config.num_kv_heads} GQA",
        }
    return {"models": info, "total_params_m": sum(v["params_m"] for v in info.values())}


@app.post("/plan", response_model=PlanResponse)
async def full_plan(req: PlanRequest):
    """
    Full PMCore pipeline: Planner → Reasoner → Communicator.
    Returns task graph, risk analysis, AND stakeholder communication.
    """
    if pipeline is None:
        raise HTTPException(503, "Pipeline not ready")
    if not req.request.strip():
        raise HTTPException(400, "Request cannot be empty")

    try:
        # Update generation config from request
        pipeline.gen_config = GenerationConfig(
            max_new_tokens=req.max_tokens,
            temperature=req.temperature,
        )

        result = pipeline.run(
            request=req.request,
            comm_request=req.comm_request,
            verbose=req.verbose,
        )

        return PlanResponse(
            request=result.request,
            planner=TaskGraphResponse(
                tasks=result.planner.task_graph,
                num_tasks=result.planner.num_tasks,
                methodology=result.planner.methodology,
                duration_days=result.planner.duration_days,
                raw_output=result.planner.raw_output,
            ),
            reasoner=RiskResponse(
                risk_analysis=result.reasoner.risk_analysis,
                overall_health=result.reasoner.overall_health,
                top_risks=result.reasoner.top_risks,
                critical_path=result.reasoner.critical_path,
                raw_output=result.reasoner.raw_output,
            ),
            communicator=CommunicationResponse(
                communication=result.communicator.communication,
                comm_type=result.communicator.comm_type,
            ),
            latency_ms=result.latency_ms,
            total_ms=result.total_ms,
        )

    except Exception as e:
        raise HTTPException(500, f"Pipeline error: {str(e)}")


@app.post("/plan/quick", response_model=QuickPlanResponse)
async def quick_plan(req: QuickPlanRequest):
    """
    Quick plan: Planner + Reasoner only (no communication generation).
    Faster response, returns structured JSON only.
    Ideal for automated pipelines and WordPress plugin task breakdown.
    """
    if pipeline is None:
        raise HTTPException(503, "Pipeline not ready")

    try:
        t0 = time.time()
        latency = {}

        t1 = time.time()
        _, planner_result = pipeline._run_planner(req.request)
        latency["planner_ms"] = round((time.time() - t1) * 1000)

        t2 = time.time()
        _, reasoner_result = pipeline._run_reasoner(req.request, planner_result)
        latency["reasoner_ms"] = round((time.time() - t2) * 1000)

        latency["total_ms"] = round((time.time() - t0) * 1000)

        return QuickPlanResponse(
            request=req.request,
            planner=TaskGraphResponse(
                tasks=planner_result.task_graph,
                num_tasks=planner_result.num_tasks,
                methodology=planner_result.methodology,
                duration_days=planner_result.duration_days,
                raw_output=planner_result.raw_output,
            ),
            reasoner=RiskResponse(
                risk_analysis=reasoner_result.risk_analysis,
                overall_health=reasoner_result.overall_health,
                top_risks=reasoner_result.top_risks,
                critical_path=reasoner_result.critical_path,
                raw_output=reasoner_result.raw_output,
            ),
            latency_ms=latency,
            total_ms=latency["total_ms"],
        )

    except Exception as e:
        raise HTTPException(500, f"Pipeline error: {str(e)}")


@app.post("/communicate")
async def communicate_only(request: Request):
    """
    Generate stakeholder communication from existing plan data.
    Pass in pre-computed planner/reasoner results to get a communication.
    """
    if pipeline is None:
        raise HTTPException(503, "Pipeline not ready")

    body = await request.json()
    pm_request  = body.get("request", "")
    comm_request = body.get("comm_request", "Write a status update for stakeholders.")
    context     = body.get("context", {})

    if not pm_request:
        raise HTTPException(400, "request field required")

    try:
        from pmcore.inference import PlannerResult, ReasonerResult

        # Build minimal planner/reasoner results from provided context
        planner_result = PlannerResult(
            raw_output=json.dumps(context.get("task_graph", {})),
            task_graph=context.get("task_graph"),
            num_tasks=context.get("num_tasks", 0),
            methodology=context.get("methodology", "Hybrid"),
            duration_days=context.get("duration_days", 0),
        )
        reasoner_result = ReasonerResult(
            raw_output=json.dumps(context.get("risk_analysis", {})),
            risk_analysis=context.get("risk_analysis"),
            overall_health=context.get("overall_health", "yellow"),
            top_risks=context.get("top_risks", []),
            critical_path=context.get("critical_path", []),
        )

        _, comm_result = pipeline._run_communicator(
            pm_request, planner_result, reasoner_result, comm_request
        )

        return {
            "communication": comm_result.communication,
            "comm_type":     comm_result.comm_type,
        }

    except Exception as e:
        raise HTTPException(500, f"Error: {str(e)}")


# ── Server Entry Point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PMCORE_PORT", 8765))
    host = os.environ.get("PMCORE_HOST", "0.0.0.0")

    print(f"""
╔══════════════════════════════════════════╗
║           PMCore API v1.0                ║
║  PMPlanner + PMReasoner + PMCommunicator ║
╠══════════════════════════════════════════╣
║  Host:    {host:<31}║
║  Port:    {str(port):<31}║
║  Docs:    http://{host}:{port}/docs       ║
╚══════════════════════════════════════════╝
    """)

    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )
