# Privacy Reader

A privacy-focused, offline PDF and raw text Text-to-Speech (TTS) reader.

## Features

- **Offline Privacy**: All processing, text extraction, and speech synthesis happen locally on your machine.
- **Advanced TTS**: Uses Coqui XTTS-v2 for high-quality, natural-sounding voice cloning and speech generation.
- **Smart Sentence Tokenization**: Handles abbreviations, initials (e.g., "Dr. Smith", "A.B."), and long sentences intelligently.
- **Page-like UI**: A modern, immersive dark-mode interface designed for comfortable reading.
- **PDF & Raw Text Support**: Upload PDFs or paste custom text to read.
- **Smart Buffering**: "Preparing..." state ensures smooth playback without stutters by lookahead buffering.
- **Continuous Reading**: Seamlessly transitions between sentences and pages.
- **State Persistence**: Remembers your reading position (page and sentence) for each book.
- **Collapsible Sidebar**: Immerse yourself in reading by hiding the library and settings.
- **Direct Page Jump**: Quickly navigate through large PDFs.
- **Automated Resource Management**: Automatically cleans up temporary audio files and shuts down the backend when you close the browser.

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **TTS Engine**: Coqui TTS (XTTS-v2)
- **PDF Processing**: PyMuPDF (fitz)

## Setup & Running

1. **Install Dependencies**:
   Ensure you have Python 3.9+ installed. It's recommended to use a virtual environment.
   ```bash
   pip install -r requirements.txt
   ```
2. **Add Reference Voice**:
   Place a 5-10 second `.wav` file named `sample_voice.wav` in the root directory for voice cloning.
3. **Run the App**:
   Double-click `run.bat` (on Windows) or run:
   ```bash
   uv run uvicorn src.backend.main:app --host 0.0.0.0 --port 8000
   ```
4. **Access UI**:
   Open your browser and go to `http://localhost:8000`.

## License

MIT
