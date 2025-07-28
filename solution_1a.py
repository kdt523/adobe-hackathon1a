import pdfplumber
import os
import json
import re
from collections import Counter, defaultdict

# --- Configuration for the REPORT Parser ---
WEIGHTS = {
    "is_bold": 3.5,
    "size_ratio": 2.0,
    "starts_with_number": 4.0,
    "is_all_caps": 1.0,
    "is_centered": 1.5,
    "line_length_penalty": -0.1
}
HEADING_THRESHOLD = 4.0

def classify_document_type(pdf):
    """Classifies the document as a 'REPORT' or 'POSTER' based on simple heuristics."""
    if len(pdf.pages) > 1:
        return 'REPORT'
    
    page = pdf.pages[0]
    text_area = sum(char['width'] * char['height'] for char in page.chars)
    page_area = page.width * page.height
    text_density = text_area / page_area if page_area > 0 else 0
    
    if len(pdf.pages) == 1 and text_density < 0.2:
        return 'POSTER'
        
    return 'REPORT'

def reconstruct_lines(page, column_gap_threshold=20):
    """
    Reconstructs lines from words, splitting them if a large horizontal gap is detected.
    This correctly handles multi-column layouts.
    """
    lines = defaultdict(list)
    words = page.extract_words(extra_attrs=["fontname", "size"])
    
    # Cluster words by vertical position
    for w in words:
        lines[round(w['top'])].append(w)
        
    # Process each cluster into one or more lines based on horizontal gaps
    reconstructed_lines = []
    for top in sorted(lines.keys()):
        sorted_words = sorted(lines[top], key=lambda w: w['x0'])
        
        current_line = []
        for i, word in enumerate(sorted_words):
            if current_line:
                # Check for large horizontal gap to detect columns
                prev_word = current_line[-1]
                gap = word['x0'] - prev_word['x1']
                if gap > column_gap_threshold:
                    # Finish the current line and start a new one
                    reconstructed_lines.append(current_line)
                    current_line = []
            current_line.append(word)
        reconstructed_lines.append(current_line) # Add the last line
        
    return reconstructed_lines

def parse_as_poster(pdf):
    """A parser for single-page documents that finds a title and a single main headline."""
    page = pdf.pages[0]
    words = page.extract_words(extra_attrs=["size"])
    if not words:
        return {"title": "", "outline": []}

    # Find the top two largest font sizes
    unique_sizes = sorted(list(set(w['size'] for w in words)), reverse=True)
    
    title_size = unique_sizes[0] if len(unique_sizes) > 0 else None
    headline_size = unique_sizes[1] if len(unique_sizes) > 1 else None

    # The largest font text becomes the title
    title_words = [w for w in words if w['size'] == title_size]
    title_words.sort(key=lambda w: (w['top'], w['x0']))
    title = ' '.join(w['text'] for w in title_words)
    
    outline = []
    # The second-largest font text becomes the H1 headline
    if headline_size:
        headline_words = [w for w in words if w['size'] == headline_size]
        headline_words.sort(key=lambda w: (w['top'], w['x0']))
        headline_text = ' '.join(w['text'] for w in headline_words)
        outline.append({"level": "H1", "text": headline_text, "page": 1})
    
    return {"title": title, "outline": outline}


def parse_as_report(pdf):
    """The advanced, multi-stage parser for structured, multi-page documents."""
    # (Helper functions for noise filtering and style analysis)
    def find_headers_footers(pdf, top_margin=0.12, bottom_margin=0.90):
        line_counts = Counter()
        for page in pdf.pages:
            header_bbox = (0, 0, page.width, page.height * top_margin)
            footer_bbox = (0, page.height * bottom_margin, page.width, page.height)
            header_text = page.crop(header_bbox).extract_text(x_tolerance=2)
            footer_text = page.crop(footer_bbox).extract_text(x_tolerance=2)
            for line in (header_text or "").split('\n'):
                if len(line.strip()) > 5: line_counts[line.strip()] += 1
            for line in (footer_text or "").split('\n'):
                if len(line.strip()) > 5: line_counts[line.strip()] += 1
        return {text for text, count in line_counts.items() if count > len(pdf.pages) / 2}

    def find_toc_pages(pdf):
        toc_pages = set()
        toc_pattern = re.compile(r'.*[\s._]+\s*\d+$')
        for i, page in enumerate(pdf.pages):
            lines = page.extract_text(x_tolerance=2).split('\n')
            toc_line_count = sum(1 for line in lines if toc_pattern.match(line))
            if toc_line_count > 5: toc_pages.add(i)
        return toc_pages

    def get_body_size(pdf, non_toc_pages):
        sizes = Counter()
        for i in non_toc_pages:
            words = pdf.pages[i].extract_words(extra_attrs=["size"])
            if words: sizes.update(round(w['size']) for w in words)
        return sizes.most_common(1)[0][0] if sizes else 10
    
    # --- Main report parsing logic ---
    noise_texts = find_headers_footers(pdf)
    toc_pages = find_toc_pages(pdf)
    content_pages_indices = set(range(len(pdf.pages))) - toc_pages
    if not content_pages_indices: return {"title": "", "outline": []}
    
    body_size = get_body_size(pdf, content_pages_indices)
    headings, title_candidates = [], []

    for page_num in sorted(list(content_pages_indices)):
        page = pdf.pages[page_num]
        
        # Use the improved line reconstruction
        reconstructed_lines = reconstruct_lines(page)

        for line_words in reconstructed_lines:
            if not line_words: continue
            line_text = ' '.join(w['text'] for w in line_words).strip()
            if not line_text or line_text in noise_texts: continue
            
            span = line_words[0]
            features = {
                "text": line_text, "size": span["size"], "page": page_num + 1,
                "is_bold": any("bold" in span["fontname"].lower() for x in ["bold", "black"]),
                "size_ratio": span["size"] / body_size,
                "starts_with_number": bool(re.match(r"^\d+(\.\d+)*\s|^Appendix\s+[A-Z]", line_text)),
                "is_all_caps": line_text.isupper() and len(line_text) > 1,
                "line_length": len(line_words),
                "is_centered": abs(((line_words[0]['x0'] + line_words[-1]['x1']) / 2 / page.width) - 0.5) < 0.15
            }
            score = 0
            if features["is_bold"]: score += WEIGHTS["is_bold"]
            if features["size_ratio"] > 1.15: score += (features["size_ratio"] * WEIGHTS["size_ratio"])
            if features["starts_with_number"]: score += WEIGHTS["starts_with_number"]
            if features["is_all_caps"]: score += WEIGHTS["is_all_caps"]
            if features["is_centered"]: score += WEIGHTS["is_centered"]
            score += features["line_length"] * WEIGHTS["line_length_penalty"]

            if score >= HEADING_THRESHOLD:
                headings.append(features)
            if page_num == min(content_pages_indices) and features["size_ratio"] > 1.5:
                 title_candidates.append(features)

    title = max(title_candidates, key=lambda x: x['size'])['text'] if title_candidates else ""
    headings = [h for h in headings if h['text'] != title]
    
    outline = []
    if headings:
        unique_headings = []
        seen_texts = set()
        for h in headings:
            if h["text"] not in seen_texts:
                unique_headings.append(h)
                seen_texts.add(h["text"])
        
        heading_sizes = sorted(list(set(h["size"] for h in unique_headings)), reverse=True)
        size_map = {size: f"H{i+1}" for i, size in enumerate(heading_sizes[:3])}
        for h in unique_headings:
            level = size_map.get(h["size"], "H3")
            outline.append({"level": level, "text": h["text"], "page": h["page"]})
    
    return {"title": title, "outline": outline}


def process_pdf(pdf_path):
    """Controller function: classifies the PDF and runs the appropriate parser."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            doc_type = classify_document_type(pdf)
            
            if doc_type == 'REPORT':
                return parse_as_report(pdf)
            elif doc_type == 'POSTER':
                return parse_as_poster(pdf)
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return None

def main():
    """Main execution block."""
    input_dir = "input"
    output_dir = "output"
    if not os.path.exists(output_dir): os.makedirs(output_dir)
        
    for filename in os.listdir(input_dir):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, os.path.splitext(filename)[0] + ".json")
            print(f"Processing {pdf_path}...")
            if structured_data := process_pdf(pdf_path):
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(structured_data, f, ensure_ascii=False, indent=4)
                print(f"Successfully generated {output_path}")

if __name__ == "__main__":
    main()