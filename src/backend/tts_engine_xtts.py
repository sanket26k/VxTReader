import os
import torch
from TTS.api import TTS

class XTTSEngine:
    def __init__(self, model_name="tts_models/multilingual/multi-dataset/xtts_v2"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading XTTS model on {self.device}...")
        self.tts = TTS(model_name).to(self.device)
        self.name = "xtts"
        print("XTTS loaded successfully.")

    def synthesize(self, text: str, reference_wav_path: str, output_wav_path: str, language="en", speed=1.0):
        if not os.path.exists(reference_wav_path):
            raise FileNotFoundError(f"Reference audio not found: {reference_wav_path}")

        # XTTS v2 doesn't natively support speed argument in tts_to_file
        self.tts.tts_to_file(
            text=text,
            speaker_wav=reference_wav_path,
            language=language,
            file_path=output_wav_path
        )
        return output_wav_path
