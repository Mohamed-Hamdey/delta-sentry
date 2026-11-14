"""
Delta Sentry — Prithvi-EO inference for Hugging Face Spaces (Gradio SDK + ZeroGPU).

Endpoints (same contract as the original demo):
    GET  /api/health   -> { ok, device, model, warmed }
    POST /api/infer    -> { status: 'completed', cached, result }

Differences from the demo version:
  - No threading. ZeroGPU kills the container on background threads (Fix #5).
  - No /job/{id} poll. The call is synchronous inside @spaces.GPU.
  - Model loading / inference delegated to inference.py (your fine-tuned b3_best.pt),
    not the base ibm-nasa-geospatial/Prithvi-EO-2.0-300M-TL.
  - Routes are namespaced under /api so /site can own its own prefix.
"""

import os
os.environ["GRADIO_SSR_MODE"] = "False"          # must run before gradio import

import spaces                                     # must import before torch / inference
import gradio as gr
import inference
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


# ---------------------------------------------------------------- contract
class InferRequest(BaseModel):
    tile_id: str
    target_month: str
    bbox: dict


# ---------------------------------------------------------------- GPU call
# Decorator on a function that is *bound to a Gradio event* below — this is what
# ZeroGPU's startup scan looks for. A decorated function that is never bound
# is invisible to the scan and you get "No @spaces.GPU function detected".
@spaces.GPU(duration=120)
def run_prithvi(tile_id: str, target_month: str, bbox: dict = None, progress=gr.Progress()):
    if bbox is None:
        bbox = {"x_min": 0, "y_min": 0, "x_max": 20, "y_max": 20}

    def cb(pct, stage):
        try:
            progress(pct / 100.0, desc=stage)
        except Exception:
            pass

    return inference.run_inference(tile_id, target_month, bbox, cb)


# ---------------------------------------------------------------- gradio shell
with gr.Blocks(title="Delta Sentry") as demo:
    gr.Markdown("# Delta Sentry")
    gr.Markdown("👉 **[Open the Dashboard](/site/)**")
    tile_in  = gr.Textbox(label="Tile ID", value="tile_001")
    month_in = gr.Textbox(label="Target month", value="2026-11")
    run_btn  = gr.Button("Run Prithvi")
    out_json = gr.JSON(label="Result")
    run_btn.click(fn=run_prithvi, inputs=[tile_in, month_in], outputs=out_json)


# ---------------------------------------------------------------- launch + routes
# prevent_thread_lock=True so we can attach routes to demo.app BEFORE blocking.
# Never use gr.mount_gradio_app() — it breaks @spaces.GPU detection on ZeroGPU.
demo.launch(
    prevent_thread_lock=True,
    ssr_mode=False,
    server_name="0.0.0.0",
    server_port=7860,
)

app = demo.app


@app.get("/api/health")
def api_health():
    return {
        "ok": True,
        "device": inference.INFERENCE_DEVICE,
        "model": inference.MODEL_VERSION,
        "warmed": inference._MODEL is not None,
    }


@app.post("/api/infer")
def api_infer(req: InferRequest):
    # Synchronous — @spaces.GPU holds the session open for up to 120 s, which
    # is enough for the one-time 1.17 GB load + inference. No threading.
    result = run_prithvi(req.tile_id, req.target_month, req.bbox)
    return {
        "status": "completed",
        "cached": result.get("cached", False),
        "result": result,
    }


# ---------------------------------------------------------------- static dashboard
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")
if os.path.isdir(SITE_DIR):
    app.mount("/site", StaticFiles(directory=SITE_DIR, html=True), name="site")


# ---------------------------------------------------------------- keep alive
demo.block_thread()