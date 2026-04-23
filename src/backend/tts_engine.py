import os
import torch
from TTS.api import TTS

class TTSEngine:
    def __init__(self, model_name="tts_models/multilingual/multi-dataset/xtts_v2"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading TTS model on {self.device}...")
        
        # Load normally to device. FP16 autocast caused CUDA device-side asserts on this specific hardware.
        self.tts = TTS(model_name).to(self.device)
        print("Model loaded successfully.")

    def synthesize(self, text: str, reference_wav_path: str, output_wav_path: str, language="en"):
        if not os.path.exists(reference_wav_path):
            raise FileNotFoundError(f"Reference audio not found: {reference_wav_path}")

        self.tts.tts_to_file(
            text=text,
            speaker_wav=reference_wav_path,
            language=language,
            file_path=output_wav_path
        )
        return output_wav_path


