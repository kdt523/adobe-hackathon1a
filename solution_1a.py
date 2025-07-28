# solution_1a.py

import pdfplumber
import os
import json
import re
from collections import Counter, defaultdict

# --- ADVANCED HEURISTIC CONFIGURATION ---
# These settings are tuned to better identify headings in complex reports.
# We add heavy penalties for things that look like sentences.
WEIGHTS = {
    "size_ratio": 3.0,
    "is_bold": 2.5,
    "is_all_caps": 1.5,
    "starts_with_number_or_appendix": 2.0,
    "is_short_line": 1.5,       # Reward for being short and punchy
    "ends_with_colon": 1.0,     # Titles like "Summary:" are common
    "ends_with_period": -5.0,   # Heavy penalty for being a full sentence
    "is_long_list_item": -5.0   # Heavy penalty for being a numbered paragraph
}
HEADING_THRESHOLD = 4.5  # A higher bar to qualify as a heading

def clean_garbled_text(text):
    """Fixes text with repeated characters, like 'RRRReeeeqqq...'"""
    # First pass for long repeats
    cleaned = re.sub(r'(.)\1{2,}', r'\1', text)
    # Second, more gentle pass for double letters to avoid breaking words like "Proposal"
    cleaned = re.sub(r'([a-zA-Z])\1\1', r'\1', cleaned)
    # Common spacing fixes found in the example
    cleaned = re.sub(r'\s*:\s*', ': ', cleaned)
    return cleaned.strip()


def get_document_style_profile(pdf, content_pages):
    """Analyzes the document to find common font sizes, bold fonts, and the main title."""
    sizes = Counter()
    font_names = Counter()
    title_candidates = []

    # Analyze the style of the first few content pages
    for i in list(content_pages)[:3]:
        page = pdf.pages[i]
        words = page.extract_words(extra_attrs=["fontname", "size"])
        if not words: continue
        sizes.update(round(w['size'], 1) for w in words)
        font_names.update(w['fontname'].lower() for w in words)

    # The most frequent size is the body text
    body_size = sizes.most_common(1)[0][0] if sizes else 10.0
    # A font is bold if 'bold' or a similar indicator is in its name
    bold_fonts = {name for name, count in font_names.items() if any(indicator in name for indicator in ["bold", "black", "oblique", "cn"])}

    # Title is likely the largest text on the first content page
    first_page = pdf.pages[min(content_pages)]
    words = first_page.extract_words(extra_attrs=["size"])
    if words:
        max_size = max(w['size'] for w in words)
        # Gather all text fragments that are significantly larger than body text
        title_words = [w for w in words if w['size'] > body_size * 1.5 and w['size'] >= max_size * 0.9]
        if title_words:
            # Reconstruct title based on reading order (top-to-bottom, left-to-right)
            title_words.sort(key=lambda w: (w['top'], w['x0']))
            raw_title = ' '.join(w['text'] for w in title_words)
            title = clean_garbled_text(raw_title)
        else:
            title = ""
    else:
        title = ""

    return body_size, bold_fonts, title

def find_noise_and_content_pages(pdf):
    """Identifies and removes headers, footers, and tables of contents."""
    noise_texts = set()
    line_counts = Counter()
    toc_pages = set()
    toc_pattern = re.compile(r'.+[\s._]+\s*\d+$')

    for i, page in enumerate(pdf.pages):
        # Identify headers/footers (text repeated on >50% of pages)
        top_box = (0, 0, page.width, page.height * 0.12)
        bottom_box = (0, page.height * 0.90, page.width, page.height)
        header_text = page.crop(top_box).extract_text(x_tolerance=2)
        footer_text = page.crop(bottom_box).extract_text(x_tolerance=2)
        for line in (header_text or "").split('\n') + (footer_text or "").split('\n'):
            if line.strip(): line_counts[line.strip()] += 1
        
        # Identify ToC pages (many lines ending in a page number)
        lines = page.extract_text(x_tolerance=2).split('\n')
        toc_line_count = sum(1 for line in lines if toc_pattern.match(line) and len(line) < 100)
        if toc_line_count > len(lines) * 0.2 and toc_line_count > 4:
            toc_pages.add(i)

    # Filter out text that appears on more than half the pages
    for text, count in line_counts.items():
        if count > len(pdf.pages) / 2:
            noise_texts.add(text)

    content_pages = set(range(len(pdf.pages))) - toc_pages
    return noise_texts, content_pages


def parse_as_report(pdf):
    """An advanced, context-aware parser for structured reports."""
    if not pdf.pages:
        return {"title": "", "outline": []}
        
    noise_texts, content_pages = find_noise_and_content_pages(pdf)
    if not content_pages:
        # If all pages are ToC, try to parse anyway
        content_pages = set(range(len(pdf.pages)))

    body_size, bold_fonts, title = get_document_style_profile(pdf, content_pages)
    
    headings = []

    for page_num in sorted(list(content_pages)):
        page = pdf.pages[page_num]
        lines = page.extract_text_lines(layout=True, strip=True)

        for line in lines:
            line_text = line['text'].strip()
            
            # Filter out noise and irrelevant lines
            if not line_text or line_text in noise_texts or line_text.isdigit():
                continue

            # Feature Extraction from the line
            first_char = line['chars'][0] if line['chars'] else {}
            font_size = first_char.get('size', body_size)
            font_name = first_char.get('fontname', '').lower()

            features = {
                "size_ratio": font_size / body_size,
                "is_bold": any(indicator in font_name for indicator in ["bold", "black", "cn", "oblique"]),
                "starts_with_number_or_appendix": bool(re.match(r"^\d+(\.\d+)*\s*|^[IVX]+\.\s*|^Appendix\s+[A-Z]", line_text)),
                "is_all_caps": line_text.isupper() and len(line_text) > 1 and " " in line_text,
                "is_short_line": len(line_text.split()) < 10,
                "ends_with_colon": line_text.endswith(':'),
                "ends_with_period": line_text.endswith('.'),
                "is_long_list_item": (bool(re.match(r"^\d+\.\d+", line_text)) and len(line_text.split()) > 8)
            }

            # Calculate a score based on how "heading-like" the line is
            score = 0
            if features["size_ratio"] > 1.1: score += features["size_ratio"] * WEIGHTS["size_ratio"]
            if features["is_bold"]: score += WEIGHTS["is_bold"]
            if features["is_all_caps"]: score += WEIGHTS["is_all_caps"]
            if features["starts_with_number_or_appendix"]: score += WEIGHTS["starts_with_number_or_appendix"]
            if features["is_short_line"]: score += WEIGHTS["is_short_line"]
            if features["ends_with_colon"]: score += WEIGHTS["ends_with_colon"]
            if features["ends_with_period"]: score += WEIGHTS["ends_with_period"]
            if features["is_long_list_item"]: score += WEIGHTS["is_long_list_item"]

            if score >= HEADING_THRESHOLD:
                headings.append({"text": line_text, "size": round(font_size, 1), "page": page_num + 1})

    # --- Post-processing to build the final outline ---
    # 1. Filter out duplicates and any heading text that is part of the title
    final_headings = []
    seen_texts = {t.lower() for t in title.split('\n')}
    for h in headings:
        if h["text"].lower() not in seen_texts:
            final_headings.append(h)
            seen_texts.add(h["text"].lower())

    # 2. Assign H1-H4 levels based on a dynamic hierarchy of font sizes
    # This makes the level assignment robust and not fixed to 3 levels
    if not final_headings:
        return {"title": title, "outline": []}

    unique_sizes = sorted(list(set(h["size"] for h in final_headings)), reverse=True)
    size_map = {size: f"H{i+1}" for i, size in enumerate(unique_sizes[:4])}
    
    outline = []
    for h in final_headings:
        # Default to H4 for sizes outside the top 4
        level = size_map.get(h["size"], "H4")
        outline.append({"level": level, "text": h["text"], "page": h["page"]})

    return {"title": title, "outline": outline}


def process_pdf(pdf_path):
    """Main controller function: opens the PDF and runs the parser."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return parse_as_report(pdf)
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return None

def main():
    """Main execution block. Finds PDFs in ./input and writes JSON to ./output."""
    input_dir = "input"
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
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