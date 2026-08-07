import re

def recursive_character_split(text: str, chunk_size: int = 700, chunk_overlap: int = 150) -> list[str]:
    """
    Professional chunking strategy: attempts to split by double newline (paragraphs), 
    then single newline, then periods, then spaces, to preserve semantic meaning.
    
    Optimized for sentence-transformers models (all-MiniLM-L6-v2) which have a ~256-token
    (~700-800 character) context limit to prevent vector truncation.
    """
    separators = ["\n\n", "\n", ". ", " ", ""]
    
    for separator in separators:
        if separator == "":
            chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size - chunk_overlap)]
            return [c for c in chunks if c.strip()]
            
        splits = text.split(separator)
        if all(len(s) <= chunk_size for s in splits):
            break
            
    # Reassemble chunks with overlap
    chunks = []
    current_chunk = []
    current_length = 0
    
    for split in splits:
        split_len = len(split) + (len(separator) if current_chunk else 0)
        if current_length + split_len > chunk_size and current_chunk:
            # Join current chunk and add to results
            chunks.append(separator.join(current_chunk))
            # Keep overlap: keep last few items from current_chunk
            overlap_length = 0
            overlap_chunk = []
            for item in reversed(current_chunk):
                if overlap_length + len(item) <= chunk_overlap:
                    overlap_chunk.insert(0, item)
                    overlap_length += len(item) + len(separator)
                else:
                    break
            current_chunk = overlap_chunk
            current_length = sum(len(c) for c in current_chunk) + (len(separator) * max(0, len(current_chunk) - 1))
            
        current_chunk.append(split)
        current_length += split_len
        
    if current_chunk:
        chunks.append(separator.join(current_chunk))
        
    return chunks

def process_document_to_chunks(parsed_pages: list[dict], chunk_size: int = 700, chunk_overlap: int = 150) -> list[dict]:
    """Takes parsed pages and chunks them while retaining source metadata."""
    final_chunks = []
    for page in parsed_pages:
        text_chunks = recursive_character_split(page["content"], chunk_size, chunk_overlap)
        for chunk in text_chunks:
            if len(chunk.strip()) > 30: # Ignore tiny useless chunks
                final_chunks.append({
                    "content": chunk.strip(),
                    "metadata": page["metadata"]
                })
    return final_chunks