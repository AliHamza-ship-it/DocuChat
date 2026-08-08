import re

def is_header_line(line: str) -> bool:
    """Detects structural headers such as 'Week 3', 'Day 4', 'Module 1', '# Heading', etc."""
    line_clean = re.sub(
        r"^[•●▪◦\-\*]\s*",
        "",
        line.strip()
    )
    if not line_clean or len(line_clean) > 80:
        return False
    
    header_patterns = [
        r"^#{1,6}\s+.+",                                           # Markdown headers
        r"^(?:week|day|module|chapter|unit|section|part)\s+\d+\b.*",  # Week 1, Day 2, etc.
        r"^[A-Z0-9\s\-_]{2,50}:$"                                  # Capitalized title ending with colon
    ]
    for pattern in header_patterns:
        if re.match(pattern, line_clean, re.IGNORECASE):
            return True
    return False

def recursive_character_split(text: str, chunk_size: int = 700, chunk_overlap: int = 150) -> list[str]:
    """
    Splits text recursively preserving sentence boundaries.
    Optimized for sentence-transformers (~256-token limit) to prevent vector truncation.
    """
    separators = ["\n\n", "\n", ". ", " ", ""]
    
    for separator in separators:
        if separator == "":
            chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size - chunk_overlap)]
            return [c for c in chunks if c.strip()]
            
        splits = text.split(separator)
        if all(len(s) <= chunk_size for s in splits):
            break
            
    chunks = []
    current_chunk = []
    current_length = 0
    
    for split in splits:
        split_len = len(split) + (len(separator) if current_chunk else 0)
        if current_length + split_len > chunk_size and current_chunk:
            chunks.append(separator.join(current_chunk))
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
    """
    Processes parsed document pages using Contextual Breadcrumb Enrichment.
    Tracks structural headings across pages and prepends parent context ([Header Context: Week X > Day Y])
    directly into chunk content before embedding.
    """
    final_chunks = []
    active_breadcrumbs = []
    
    for page in parsed_pages:
        raw_text = page["content"]
        metadata = page["metadata"].copy()
        
        lines = raw_text.split("\n")
        
        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue
                
            if is_header_line(line_clean):
                # Parent structural elements (e.g., Week, Module, Chapter)
                if re.match(r"^(?:week|module|chapter|unit|part)\s+\d+", line_clean, re.IGNORECASE) or line_clean.startswith("# "):
                    active_breadcrumbs = [line_clean]
                # Child elements (e.g., Day, Section)
                elif re.match(r"^(?:day|section)\s+\d+", line_clean, re.IGNORECASE) or line_clean.startswith("##"):
                    if len(active_breadcrumbs) > 0:
                        active_breadcrumbs = [active_breadcrumbs[0], line_clean]
                    else:
                        active_breadcrumbs = [line_clean]
                else:
                    active_breadcrumbs = [line_clean]

        text_chunks = recursive_character_split(raw_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        context_prefix = ""
        if active_breadcrumbs:
            context_prefix = f"[Header Context: {' > '.join(active_breadcrumbs)}]\n"
        
        for chunk in text_chunks:
            if len(chunk.strip()) > 30:
                enriched_content = f"{context_prefix}{chunk.strip()}" if context_prefix and not chunk.startswith("[Header Context:") else chunk.strip()
                
                chunk_meta = metadata.copy()
                if active_breadcrumbs:
                    chunk_meta["breadcrumbs"] = " > ".join(active_breadcrumbs)
                
                final_chunks.append({
                    "content": enriched_content,
                    "metadata": chunk_meta
                })
                
    return final_chunks