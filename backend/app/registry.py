"""Backend registry: the slices in pipeline order. Not edited after the skeleton."""
from app.features.analysis.router import router as analysis_router
from app.features.analysis.run import run as run_analysis
from app.features.evidence.router import router as evidence_router
from app.features.evidence.run import run as run_evidence
from app.features.feedback.router import router as feedback_router
from app.features.feedback.run import run as run_feedback
from app.features.investigator.router import router as investigator_router
from app.features.investigator.run import run as run_investigator
from app.features.scene.router import router as scene_router
from app.features.scene.run import run as run_scene

# (slice, run, router, UI stages it covers)
SLICES = [
    ("evidence", run_evidence, evidence_router, ["ingest", "extract"]),
    ("scene", run_scene, scene_router, []),
    ("analysis", run_analysis, analysis_router, ["resolve", "graph", "detect"]),
    ("investigator", run_investigator, investigator_router, ["verify", "analyze"]),
    ("feedback", run_feedback, feedback_router, ["critique"]),  # last: questions for the detective (Person 1)
]
STAGES = [stage for _, _, _, stages in SLICES for stage in stages]
