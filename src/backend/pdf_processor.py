import fitz  # PyMuPDF
import re
import os

class PDFProcessor:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.doc = fitz.open(file_path)
    
    def get_num_pages(self):
        return len(self.doc)

    def extract_page_blocks(self, page_num: int) -> list[str]:
        if page_num < 0 or page_num >= len(self.doc):
            return []
            
        page = self.doc[page_num]
        blocks = page.get_text("blocks")
        text_blocks = [b[4] for b in blocks if b[6] == 0]
        
        cleaned_blocks = []
        for text in text_blocks:
            cleaned = self.clean_text(text)
            if cleaned:
                cleaned_blocks.append(cleaned)
                
        return cleaned_blocks

    @staticmethod
    def clean_text(text: str) -> str:
        # 1. Normalize common PDF ligatures
        ligatures = {
            "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
            "’": "'", "‘": "'", "”": '"', "“": '"', "–": "-", "—": "-"
        }
        for k, v in ligatures.items():
            text = text.replace(k, v)

        # 2. Basic cleaning (newlines, tabs)
        text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        
        # 3. Remove overstriking (common in bold PDF text where chars are doubled: 'TThhee')
        # We only do this if we see a pattern of repeated characters in a word
        def de_overstrike(m):
            word = m.group(0)
            if len(word) > 2:
                # Check if even/odd characters are identical
                even = word[0::2]
                odd = word[1::2]
                if even == odd:
                    return even
            return word
        
        # Only attempt on words that look like they might be overstruck
        text = re.sub(r'\b(\w\w){2,}\b', de_overstrike, text)

        # 4. Filter to keep only standard ASCII alphanumeric and basic punctuation
        # This removes control characters and weird math/symbols that confuse TTS
        text = re.sub(r'[^a-zA-Z0-9\s.,!?;:\-\'\"()\[\]]', '', text)
        
        # 5. Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()

    @staticmethod
    def get_sentences(blocks: list[str], page_idx: int = 0) -> list[dict]:
        final_sentences = []
        for block_idx, block in enumerate(blocks):
            # Protect initials and common titles
            protected = re.sub(r'\b([A-Z])\.', r'\1<DOT>', block)
            protected = re.sub(r'\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St)\.', r'\1<DOT>', protected)
            
            # Split
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', protected)
            
            for s_idx, s in enumerate(sentences):
                s = s.replace('<DOT>', '.').strip()
                if not s: continue
                
                is_new_paragraph = (s_idx == 0 and block_idx > 0)
                
                # Chunk long sentences
                if len(s) > 250:
                    chunks = re.split(r'(?<=[,;])\s+', s)
                    current_chunk = ""
                    for i, chunk in enumerate(chunks):
                        if len(current_chunk) + len(chunk) > 250 and current_chunk:
                            final_sentences.append({
                                "text": current_chunk.strip(), 
                                "is_new_paragraph": is_new_paragraph and i == 0,
                                "page": page_idx,
                                "rel_idx": len(final_sentences)
                            })
                            current_chunk = chunk
                        else:
                            current_chunk += " " + chunk if current_chunk else chunk
                    if current_chunk:
                        final_sentences.append({
                            "text": current_chunk.strip(), 
                            "is_new_paragraph": is_new_paragraph and len(chunks) == 1,
                            "page": page_idx,
                            "rel_idx": len(final_sentences)
                        })
                else:
                    final_sentences.append({
                        "text": s, 
                        "is_new_paragraph": is_new_paragraph,
                        "page": page_idx,
                        "rel_idx": len(final_sentences)
                    })
                    
        return final_sentences
        
    def close(self):
        self.doc.close()


