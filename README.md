# Privacy Reader

A privacy-focused, offline PDF and raw text Text-to-Speech (TTS) reader.

## Features

- **Offline Privacy**: All processing, text extraction, and speech synthesis happen locally on your machine.
- **Advanced TTS**: Uses Coqui XTTS-v2 for high-quality, natural-sounding voice cloning and speech generation.
- **Smart Sentence Tokenization**: Handles abbreviations, initials (e.g., "Dr. Smith", "A.B."), and long sentences intelligently.
- **Page-like UI**: A modern, immersive dark-mode interface designed for comfortable reading.
- **PDF & Raw Text Support**: Upload PDFs or paste custom text to read. Switch between a clean text view and a native PDF viewer at the click of a button.
- **Smart Buffering**: "Preparing..." state ensures smooth playback without stutters by utilizing a background lookahead buffer.
- **Continuous Reading**: Seamlessly transitions between sentences and dynamically flips pages automatically.
- **State Persistence**: Remembers your exact reading position (page and sentence) for each book across sessions.
- **Collapsible Sidebar**: Immerse yourself in reading by hiding the library and settings.
- **Direct Page Jump**: Quickly navigate through large PDFs by typing a page number into the pagination box.
- **Automated Resource Management**: Automatically cleans up temporary audio files and securely shuts down the background Python server when you close the browser tab.

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
   Double-click `run.bat` (on Windows). 
   - The script will automatically clear any hanging processes on the required port.
   - The FastAPI backend will load the XTTS model into your GPU.
   - Once initialized, it will **automatically open** `http://localhost:8000` in your default web browser.

## License

MIT
