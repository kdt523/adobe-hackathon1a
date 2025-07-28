# solution_1a.py

import pdfplumber
import os
import json
import re
from collections import Counter, defaultdict

def clean_and_normalize_text(text):
    """Cleans text, normalizes whitespace, and handles common unicode artifacts."""
    if not text:
        return ""
    # More aggressive garbled text cleaning
    cleaned = re.sub(r'(.)\1{2,}', r'\1', text)
    cleaned = re.sub(r'([a-zA-Z])\1\1', r'\1', cleaned)
    # Standardize all forms of whitespace to a single space
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Fix common OCR/extraction errors for this document
    replacements = {
        'Sumary': 'Summary', 'Aces': 'Access', 'Apendix': 'Appendix',
        'Busines': 'Business', 'Planing': 'Planning', 'Comite': 'Committee',
        'Stering': 'Steering', 'Aproach': 'Approach'
    }
    for wrong, right in replacements.items():
        cleaned = cleaned.replace(wrong, right)
    return cleaned

def find_common_styles_and_noise(pdf):
    """Analyzes the document to find body text size and recurring header/footer text."""
    sizes = Counter()
    line_counts = Counter()
    
    # Analyze a sample of pages to determine common styles
    page_sample = pdf.pages[1:5] if len(pdf.pages) > 5 else pdf.pages
    for page in page_sample:
        words = page.extract_words(extra_attrs=["size"])
        if words:
            sizes.update(round(w['size'], 1) for w in words)

    # Scan all pages for headers and footers
    for page in pdf.pages:
        # Define a tighter BBox for headers/footers
        header_box = (0, 0, page.width, page.height * 0.10)
        footer_box = (0, page.height * 0.92, page.width, page.height)
        # Use a more tolerant text extraction setting for noisy areas
        header_text = page.crop(header_box).extract_text(x_tolerance=3, y_tolerance=3)
        footer_text = page.crop(footer_box).extract_text(x_tolerance=3, y_tolerance=3)
        
        for line in (header_text or "").split('\n') + (footer_text or "").split('\n'):
            # Match the core part of the recurring text, ignoring page numbers
            match = re.match(r'^(.*\D)\s*\d*\s*$', line.strip())
            if match:
                cleaned_line = clean_and_normalize_text(match.group(1))
                if cleaned_line and len(cleaned_line) > 10:
                    line_counts[cleaned_line] += 1

    body_size = sizes.most_common(1)[0][0] if sizes else 10.0
    # A line is considered noise if it appears on at least 3 pages or > 30% of pages
    noise_threshold = max(3, len(pdf.pages) * 0.3)
    noise_texts = {text for text, count in line_counts.items() if count >= noise_threshold}
    
    return body_size, noise_texts

def get_title_and_cover_elements(page, body_size):
    """Extracts the multi-line title and identifies all text on the cover page to be ignored."""
    words = page.extract_words(extra_attrs=["size"])
    if not words: return "", set()

    max_size = 0
    for w in words:
        if w['size'] > max_size:
            max_size = w['size']
    
    # Title consists of all text blocks with font size close to the maximum
    title_words = [w for w in words if w['size'] >= max_size * 0.75]
    title_words.sort(key=lambda w: (w['top'], w['x0']))
    
    # Reconstruct lines based on vertical position
    lines = defaultdict(list)
    for word in title_words:
        lines[word['top']].append(word)
    
    full_title_parts = []
    for top in sorted(lines.keys()):
        line_text = ' '.join(word['text'] for word in sorted(lines[top], key=lambda w: w['x0']))
        full_title_parts.append(line_text)

    raw_title = ' '.join(full_title_parts)
    title = clean_and_normalize_text(raw_title)

    # All text on the first page that is larger than body text is a cover element
    cover_page_elements = {clean_and_normalize_text(w['text']) for w in words if w['size'] > body_size * 1.1}
    
    return title, cover_page_elements

def is_likely_heading(line, body_size, noise_texts):
    """Determines if a line of text is a heading using a strict set of rules."""
    text = clean_and_normalize_text(line['text'])

    # --- Strict Filtering ---
    if not text or text in noise_texts or text.isdigit(): return False
    if len(text.split()) > 10 or (text.endswith('.') and len(text.split()) > 6): return False
    if re.match(r"^\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\.?\s*$", text): return False
    
    char = line['chars'][0]
    font_size = char['size']
    is_bold = "bold" in char['fontname'].lower() or "black" in char['fontname'].lower()
    is_larger = font_size > body_size * 1.05
    is_all_caps = text.isupper() and len(text.split()) > 1 and not any(c.isdigit() for c in text)
    is_numbered = bool(re.match(r"^\d+(\.\d+)*\s*|^[IVX]+\.\s*|^Appendix\s+[A-Z]", text))

    if is_larger or is_bold or is_all_caps or is_numbered:
        return True
        
    return False

def main():
    """Main execution block."""
    input_dir = "input"
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
        
    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".pdf"): continue

        pdf_path = os.path.join(input_dir, filename)
        output_path = os.path.join(output_dir, f"{os.path.splitext(filename)[0]}.json")
        print(f"Processing {pdf_path}...")
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    structured_data = {"title": "Empty Document", "outline": []}
                else:
                    body_size, noise_texts = find_common_styles_and_noise(pdf)
                    title, cover_page_elements = get_title_and_cover_elements(pdf.pages[0], body_size)
                    
                    headings = []
                    for i, page in enumerate(pdf.pages):
                        # Use a more tolerant text extraction strategy for the main content
                        lines = page.extract_text_lines(layout=True, strip=True, x_tolerance=3, y_tolerance=3)
                        for line in lines:
                            if not line['chars']: continue
                            line_text_cleaned = clean_and_normalize_text(line['text'])
                            
                            # The two crucial checks: is it a heading AND not a cover page element?
                            if is_likely_heading(line, body_size, noise_texts) and line_text_cleaned not in cover_page_elements:
                                headings.append({
                                    "text": line_text_cleaned,
                                    "size": round(line['chars'][0]['size'], 1),
                                    "page": i + 1
                                })
                    
                    unique_headings = []
                    seen_texts = set()
                    for h in headings:
                        if h['text'].lower() not in seen_texts:
                            unique_headings.append(h)
                            seen_texts.add(h['text'].lower())
                    
                    if unique_headings:
                        heading_sizes = sorted(list(set(h["size"] for h in unique_headings)), reverse=True)
                        size_map = {size: f"H{i+1}" for i, size in enumerate(heading_sizes[:4])}
                        
                        outline = []
                        for h in unique_headings:
                            level = size_map.get(h["size"], "H4")
                            if h['size'] >= body_size * 0.95:
                                outline.append({"level": level, "text": h["text"], "page": h["page"]})
                    else:
                        outline = []
                        
                    structured_data = {"title": title, "outline": outline}

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(structured_data, f, ensure_ascii=False, indent=4)
            print(f"Successfully generated {output_path}")

        except Exception as e:
            print(f"!!! Error processing {pdf_path}: {e}")

if __name__ == "__main__":
    main()