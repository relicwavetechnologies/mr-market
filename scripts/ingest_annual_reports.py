#!/usr/bin/env python3
"""Ingest annual report PDFs into Qdrant for RAG-based analysis.

Usage:
    python scripts/ingest_annual_reports.py --pdf /path/to/report.pdf --ticker RELIANCE
    python scripts/ingest_annual_reports.py --dir /path/to/reports/ --ticker TCS

The script:
  1. Extracts text from PDF pages using PyMuPDF.
  2. Splits text into overlapping chunks.
  3. Generates embeddings (via OpenAI or a local model).
  4. Upserts vectors into the Qdrant collection.
"""

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "annual_reports"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """Extract text from each page of a PDF file."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        if text.strip():
            pages.append({
                "page": page_num + 1,
                "text": text.strip(),
            })
    doc.close()
    return pages


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def ingest_pdf(pdf_path: str, ticker: str) -> None:
    """Process a single PDF and ingest into Qdrant."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct

    print(f"Processing: {pdf_path}")
    pages = extract_text_from_pdf(pdf_path)
    print(f"  Extracted {len(pages)} pages")

    # Chunk all pages
    all_chunks = []
    for page_data in pages:
        chunks = chunk_text(page_data["text"])
        for chunk in chunks:
            all_chunks.append({
                "text": chunk,
                "page": page_data["page"],
                "ticker": ticker,
                "source": os.path.basename(pdf_path),
            })

    print(f"  Generated {len(all_chunks)} chunks")

    if not all_chunks:
        print("  No text content found, skipping.")
        return

    # Connect to Qdrant
    client = QdrantClient(url=QDRANT_URL)

    # Ensure collection exists (using a placeholder dimension — adjust for your embedding model)
    embedding_dim = 1536  # OpenAI text-embedding-3-small
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
        )
        print(f"  Created collection '{COLLECTION_NAME}'")

    # Generate embeddings
    # NOTE: Replace with your preferred embedding approach
    print("  Generating embeddings (placeholder — implement with your embedding model)...")
    points = []
    for i, chunk_data in enumerate(all_chunks):
        # Placeholder: random vectors for structure demonstration
        # In production, use OpenAI embeddings or a local model
        import random
        vector = [random.uniform(-1, 1) for _ in range(embedding_dim)]

        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "text": chunk_data["text"],
                    "ticker": chunk_data["ticker"],
                    "page": chunk_data["page"],
                    "source": chunk_data["source"],
                },
            )
        )

    # Upsert in batches of 100
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
        print(f"  Upserted batch {i // batch_size + 1}/{(len(points) + batch_size - 1) // batch_size}")

    print(f"  Done: {len(points)} vectors ingested for {ticker}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest annual report PDFs into Qdrant for RAG"
    )
    parser.add_argument("--pdf", help="Path to a single PDF file")
    parser.add_argument("--dir", help="Path to a directory of PDF files")
    parser.add_argument(
        "--ticker", "-t",
        required=True,
        help="NSE ticker symbol for the company",
    )
    args = parser.parse_args()

    if not args.pdf and not args.dir:
        parser.error("Provide either --pdf or --dir")

    pdf_files: list[str] = []
    if args.pdf:
        pdf_files.append(args.pdf)
    if args.dir:
        pdf_dir = Path(args.dir)
        pdf_files.extend(str(p) for p in pdf_dir.glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found.")
        sys.exit(1)

    print(f"Ingesting {len(pdf_files)} PDF(s) for ticker {args.ticker.upper()}\n")
    for pdf_path in pdf_files:
        ingest_pdf(pdf_path, args.ticker.upper())
        print()

    print("All done.")


if __name__ == "__main__":
    main()
