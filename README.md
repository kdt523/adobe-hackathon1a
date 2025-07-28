# Advanced PDF Structure Extractor

### Solution for the Adobe India Hackathon 2025: Round 1A

This project provides a robust solution for the "Understand Your Document" challenge. It implements an advanced, multi-stage pipeline to parse PDF documents, intelligently identify their structure, and extract a clean, hierarchical outline (Title and H1-H4 headings) in the required JSON format.

The core of this solution is built to be resilient against common PDF parsing challenges, such as complex layouts, inconsistent formatting, and recurring noise like headers and footers.

---

## 📂 Project Structure

The repository is organized for clarity and straightforward execution within a Docker environment.

```
.
├── input/
│   └── *.pdf                 # All PDF documents to be analyzed
│
├── output/
│   └── *.json                # The generated JSON outline for each PDF
│
├── .gitignore                # Specifies files to be excluded from Git
├── Dockerfile                # The recipe to build the containerized application
├── README.md                 # This file
├── requirements.txt          # Lists all Python dependencies
└── solution_1a.py            # The core Python script for parsing and analysis
```

## ⚙️ Core Methodology

This solution moves beyond simple heuristics like font size alone and employs a sophisticated, layout-aware approach that mimics human interpretation of a document's structure.

The parsing pipeline consists of four key stages:

1.  **Pre-processing and Noise Reduction**: The script begins by analyzing the entire document to build a typographic profile. It identifies the most common font size to determine the `body_size`. Crucially, it also scans all pages to detect and create an "ignore list" of recurring text in headers and footers, preventing this noise from contaminating the final outline.

2.  **Cover Page Isolation**: To solve the critical problem of title page elements leaking into the outline, the script treats the first page as a special case. It uses a dedicated function to identify and reconstruct the main document `title` by grouping the largest text elements. It then flags all other uniquely styled text on the cover page to be explicitly ignored during the heading detection phase.

3.  **Context-Aware Heading Detection**: The script iterates through the remaining pages, evaluating lines of text against a strict set of rules to determine if they are headings. A line is classified as a heading only if it meets strong typographic and structural criteria, such as:
    *   Being significantly larger or bolder than the body text.
    *   Being written in ALL CAPS.
    *   Being a short, standalone line (a key structural clue).
    *   Being explicitly numbered (e.g., `1. Preamble`, `Appendix A`).
    *   **Crucially, it penalizes lines that resemble full sentences, effectively filtering out paragraphs that might contain bolded words.**

4.  **Dynamic Hierarchy Assignment**: After a clean list of all true headings has been compiled, the script analyzes their font sizes. It dynamically identifies up to four of the most prominent heading sizes and maps them to `H1`, `H2`, `H3`, and `H4` levels. This adaptive approach ensures a correct hierarchy is generated even for documents that do not follow a standard H1-H3 structure.

This multi-stage process results in a highly accurate and clean structural outline that is resilient to the challenges posed by real-world, complex PDF documents.

## 🛠️ Tech Stack

| Component          | Technology / Library |
| ------------------ | -------------------- |
| **PDF Processing** | `pdfplumber`         |

## ⚡ Setup & Execution

The entire application is containerized with Docker for simple, one-command setup and guaranteed reproducibility, as per the hackathon requirements.

### Prerequisites

*   [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
*   All PDF files for analysis placed in the `./input` directory.

### 1. Build the Docker Image

Navigate to the project's root directory in your terminal and run the `build` command.

```bash
docker build --platform linux/amd64 -t adobe-1a-solution .
```

### 2. Run the Analysis

Execute the `run` command. This will start the container, which automatically processes every PDF in the `./input` directory and saves a corresponding JSON file to the `./output` directory.

*   **For Windows (PowerShell or Command Prompt):**
    ```bash
    docker run --rm -v "%cd%/input":/app/input -v "%cd%/output":/app/output --network none adobe-1a-solution
    ```

*   **For macOS or Linux:**
    ```bash
    docker run --rm -v "$(pwd)/input":/app/input -v "$(pwd)/output":/app/output --network none adobe-1a-solution
    ```

The final structured outlines will be saved as individual `.json` files in the `output` directory.
