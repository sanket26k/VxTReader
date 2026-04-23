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
        text = text.replace('\n', ' ')
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\x00-\x7F]+', '', text)
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


