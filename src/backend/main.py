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
from .tts_engine import TTSEngine

# Logging setup
logging.basicConfig(
    filename="app.log", 
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
TTS = None
pdf_processors = {}

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

@app.on_event("startup")
async def startup_event():
    global TTS
    logging.info("Initializing TTS Engine...")
    TTS = TTSEngine()
    logging.info("TTS Engine initialized.")
    
    # Auto-open browser once server is ready
    def open_browser():
        webbrowser.open("http://localhost:8000")
    threading.Timer(1.5, open_browser).start()

class SynthesisRequest(BaseModel):
    text: str

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
    sentences = proc.get_sentences(blocks)
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

@app.post("/api/synthesize")
async def synthesize_text(req: SynthesisRequest):
    if not TTS:
        raise HTTPException(status_code=503, detail="TTS Engine not loaded yet.")
    
    filename = f"{uuid.uuid4()}.wav"
    output_path = os.path.join(OUTPUT_DIR, filename)
    
    ref_voice = "sample_voice.wav"
    if not os.path.exists(ref_voice):
        raise HTTPException(status_code=400, detail="sample_voice.wav not found in root directory.")
    
    try:
        TTS.synthesize(req.text, ref_voice, output_path)
        return {"audio_url": f"/audio/{filename}", "filename": filename}
    except Exception as e:
        logging.error(f"TTS synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/wav")

@app.delete("/api/delete_audio/{filename}")
async def delete_audio(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
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
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            try: state = json.load(f)
            except: pass
    state[req.book_id] = {"page": req.page_num, "sentence_idx": req.sentence_idx}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    return {"status": "ok"}

@app.get("/api/load_state/{book_id}")
async def load_state(book_id: str):
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            try: 
                state = json.load(f)
                if book_id in state:
                    return state[book_id]
            except: pass
    return {"page": 0, "sentence_idx": 0}

@app.get("/api/library")
async def get_library():
    """Returns a list of all PDFs currently in the uploads directory and their reading progress."""
    books = []
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            try: state = json.load(f)
            except: pass
            
    if os.path.exists(UPLOADS_DIR):
        for f in os.listdir(UPLOADS_DIR):
            if f.endswith('.pdf'):
                books.append({
                    "id": f,
                    "page": state.get(f, {}).get("page", 0)
                })
    return {"books": books}

# Mount frontend
app.mount("/pdf-file", StaticFiles(directory=UPLOADS_DIR), name="pdf-file")
app.mount("/", StaticFiles(directory="src/frontend", html=True), name="frontend")


