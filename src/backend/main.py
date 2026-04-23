import os
import glob
import uuid
import json
import logging
import warnings

# Suppress annoying third-party warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*torch.utils._pytree._register_pytree_node.*")

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .pdf_processor import PDFProcessor

# Import the new TTS Engines
from .tts_engine_xtts import XTTSEngine
from .tts_engine_yourtts import YourTTSEngine

import asyncio

# Logging setup
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
TTS_ENGINES_CLASSES = {
    "xtts": XTTSEngine,
    "yourtts": YourTTSEngine
}
active_tts = None
active_tts_name = None
pdf_processors = {}

# TTS Queue
tts_queue = asyncio.Queue()
tts_status = {}  # key -> {"status": "queued"|"generating"|"ready"|"error", "filename": str}

# Directories
UPLOADS_DIR = "uploads"
OUTPUT_DIR = "output"
STATE_FILE = "history.json"
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Cleanup on startup
for f in glob.glob(os.path.join(OUTPUT_DIR, "*.wav")):
    try:
        os.remove(f)
    except:
        pass
logging.info("Cleaned output directory on startup.")

import webbrowser
import threading
import traceback

def tts_worker_sync(req, engine, ref_voice, output_path):
    try:
        return engine.synthesize(req.text, ref_voice, output_path, speed=req.speed)
    except Exception as e:
        logging.error(f"TTS synthesis failed: {traceback.format_exc()}")
        raise e

async def tts_worker_task():
    while True:
        req = await tts_queue.get()
        key = req.key
        
        if active_tts is None:
            tts_status[key] = {"status": "error", "message": "No active TTS engine"}
            tts_queue.task_done()
            continue
            
        tts_status[key] = {"status": "generating"}
        filename = f"{key}.wav"
        output_path = os.path.join(OUTPUT_DIR, filename)
        ref_voice = "sample_voice.wav"
        
        try:
            # Run the synchronous TTS generation in a threadpool so we don't block FastAPI
            await asyncio.to_thread(tts_worker_sync, req, active_tts, ref_voice, output_path)
            tts_status[key] = {"status": "ready", "audio_url": f"/audio/{filename}", "filename": filename}
        except Exception as e:
            tts_status[key] = {"status": "error", "message": str(e)}
            
        tts_queue.task_done()

@app.on_event("startup")
async def startup_event():
    global active_tts, active_tts_name
    logging.info("Initializing Default TTS Engine (XTTS)...")
    
    try:
        active_tts = XTTSEngine()
        active_tts_name = "xtts"
        logging.info("Active TTS Engine set to: xtts")
    except Exception as e:
        logging.error(f"Failed to load XTTS: {e}")
        try:
            active_tts = YourTTSEngine()
            active_tts_name = "yourtts"
        except:
            pass

    # Start background worker
    asyncio.create_task(tts_worker_task())
    
    # Auto-open browser once server is ready
    def open_browser():
        webbrowser.open("http://localhost:8000")
    threading.Timer(1.5, open_browser).start()

class SetModelRequest(BaseModel):
    model_name: str

@app.post("/api/set_model")
async def set_model(req: SetModelRequest):
    global active_tts, active_tts_name
    if req.model_name not in TTS_ENGINES_CLASSES:
        raise HTTPException(status_code=404, detail="Model not found")
        
    if active_tts_name == req.model_name:
        return {"status": "ok", "active_model": active_tts_name, "native_speed": getattr(active_tts, 'native_speed', 1.0) if active_tts else 1.0}
        
    logging.info(f"Switching TTS model to {req.model_name}...")
    
    # Unload previous model
    if active_tts is not None:
        del active_tts
        active_tts = None
        import torch
        import gc
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        
    # Load new model
    try:
        active_tts = TTS_ENGINES_CLASSES[req.model_name]()
        active_tts_name = req.model_name
        active_tts.native_speed = 1.0
    except Exception as e:
        logging.error(f"Failed to load {req.model_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load model: {e}")
        
    return {"status": "ok", "active_model": active_tts_name, "native_speed": active_tts.native_speed}

@app.get("/api/get_models")
async def get_models():
    native_speed = getattr(active_tts, 'native_speed', 1.0) if active_tts else 1.0
    return {
        "models": list(TTS_ENGINES_CLASSES.keys()),
        "active": active_tts_name,
        "native_speed": native_speed
    }

class EnqueueRequest(BaseModel):
    text: str
    key: str
    speed: float = 1.0

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOADS_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    proc = PDFProcessor(file_path)
    pdf_processors[file.filename] = proc
    logging.info(f"Uploaded and processed PDF: {file.filename}")
    
    return {"book_id": file.filename, "num_pages": proc.get_num_pages()}

@app.get("/api/book/{book_id}/page/{page_num}")
async def get_page_sentences(book_id: str, page_num: int):
    if book_id not in pdf_processors:
        file_path = os.path.join(UPLOADS_DIR, book_id)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Book not found")
        pdf_processors[book_id] = PDFProcessor(file_path)
        
    proc = pdf_processors[book_id]
    blocks = proc.extract_page_blocks(page_num)
    sentences = proc.get_sentences(blocks, page_idx=page_num)
    return {
        "sentences": sentences,
        "total_pages": proc.get_num_pages()
    }

@app.get("/api/book/{book_id}/raw")
async def get_raw_pdf(book_id: str):
    file_path = os.path.join(UPLOADS_DIR, book_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Book not found")
    return FileResponse(file_path, media_type="application/pdf")

class CustomTextRequest(BaseModel):
    text: str

@app.post("/api/custom_text")
async def process_custom_text(req: CustomTextRequest):
    # Split the raw text into paragraph blocks
    raw_blocks = [b.strip() for b in req.text.split('\n\n') if b.strip()]
    
    # Clean blocks
    cleaned_blocks = [PDFProcessor.clean_text(b) for b in raw_blocks]
    
    # Tokenize
    sentences = PDFProcessor.get_sentences(cleaned_blocks)
        
    return {"sentences": sentences}

@app.post("/api/enqueue_text")
async def enqueue_text(req: EnqueueRequest):
    if not active_tts:
        raise HTTPException(status_code=503, detail="TTS Engine not loaded yet.")
    
    # If already queued or ready, ignore
    if req.key in tts_status and tts_status[req.key]["status"] in ["queued", "generating", "ready"]:
        return {"status": tts_status[req.key]["status"]}
        
    tts_status[req.key] = {"status": "queued"}
    await tts_queue.put(req)
    
    return {"status": "queued"}

@app.get("/api/check_audio/{key}")
async def check_audio(key: str):
    if key not in tts_status:
        return {"status": "not_found"}
    return tts_status[key]

@app.post("/api/clear_queue")
async def clear_queue():
    # Empty the queue
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
            tts_queue.task_done()
        except asyncio.QueueEmpty:
            break
            
    # Keep ready items, clear queued
    for k in list(tts_status.keys()):
        if tts_status[k]["status"] == "queued":
            del tts_status[k]
            
    return {"status": "cleared"}

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/wav")

@app.delete("/api/delete_audio/{filename}")
async def delete_audio(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    
    # Also clean up from status map if it's there
    key = filename.replace(".wav", "")
    if key in tts_status:
        del tts_status[key]
        
    if os.path.exists(path):
        try:
            os.remove(path)
            return {"status": "deleted"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "not_found"}

@app.post("/api/cleanup_all")
async def cleanup_all():
    count = 0
    for f in glob.glob(os.path.join(OUTPUT_DIR, "*.wav")):
        try:
            os.remove(f)
            count += 1
        except:
            pass
    logging.info(f"Cleaned up {count} audio files on demand.")
    return {"status": "ok", "deleted": count}

@app.post("/api/shutdown")
async def shutdown():
    count = 0
    for f in glob.glob(os.path.join(OUTPUT_DIR, "*.wav")):
        try:
            os.remove(f)
            count += 1
        except:
            pass
    logging.info(f"Cleaned up {count} audio files. UI closed. Terminating server...")
    
    # Terminate the server asynchronously so the request completes
    import threading
    import time
    def kill_server():
        time.sleep(0.5)
        os._exit(0) # Forcefully kill the current python process
        
    threading.Thread(target=kill_server).start()
    return {"status": "shutting down", "deleted": count}

class StateRequest(BaseModel):
    book_id: str
    page_num: int
    sentence_idx: int

@app.post("/api/save_state")
async def save_state(req: StateRequest):
    history = {"last_opened": "", "books": {}}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            try: 
                data = json.load(f)
                # Handle migration from flat or old 'files' format
                if "books" in data:
                    history = data
                else:
                    # Migrate old top-level book entries or 'files' key
                    if "files" in data:
                        history["books"].update(data["files"])
                        del data["files"]
                    if "last_opened" in data:
                        history["last_opened"] = data["last_opened"]
                        del data["last_opened"]
                    # Any remaining keys are treated as book_ids
                    for k, v in data.items():
                        if isinstance(v, dict):
                            history["books"][k] = v
            except: pass
            
    history["last_opened"] = req.book_id
    # Ensure consistent key name 'sentence_idx'
    history["books"][req.book_id] = {"page": req.page_num, "sentence_idx": req.sentence_idx}
    
    with open(STATE_FILE, "w") as f:
        json.dump(history, f)
    return {"status": "ok"}

@app.get("/api/load_state/{book_id}")
async def load_state(book_id: str):
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            try: 
                data = json.load(f)
                books = data.get("books", data) # Fallback for old format
                if book_id in books:
                    state = books[book_id]
                    # Compatibility fix for 'sentence_index' vs 'sentence_idx'
                    return {
                        "page": state.get("page", 0),
                        "sentence_idx": state.get("sentence_idx", state.get("sentence_index", 0))
                    }
            except: pass
    return {"page": 0, "sentence_idx": 0}

@app.get("/api/library")
async def get_library():
    """Returns a list of all PDFs currently in the uploads directory and their reading progress."""
    books = []
    history_books = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            try: 
                data = json.load(f)
                history_books = data.get("books", data)
            except: pass
            
    if os.path.exists(UPLOADS_DIR):
        for f in os.listdir(UPLOADS_DIR):
            if f.endswith('.pdf'):
                books.append({
                    "id": f,
                    "page": history_books.get(f, {}).get("page", 0)
                })
    return {"books": books}

# Mount frontend
app.mount("/pdf-file", StaticFiles(directory=UPLOADS_DIR), name="pdf-file")
app.mount("/", StaticFiles(directory="src/frontend", html=True), name="frontend")


