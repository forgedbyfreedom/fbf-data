#!/usr/bin/env python3
"""
Full replacement: sync_all_to_pinecone.py
Counts and optionally uploads all transcripts from thinkbig, fbf-data, and transcripts directories.
"""

import os
import json
import time
from pathlib import Path
from tqdm import tqdm
from pinecone import Pinecone
from openai import OpenAI

# === CONFIG ===
UPLOAD = False  # set to True to sync to Pinecone
REPORT_PATH = "transcript_report.json"

SOURCE_DIRS = [
    "thinkbig-transcripts",
    "fbf-data",
    "transcripts"
]

# === ENV ===
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "forged-freedom-ai")

client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
pc = Pinecone(api_key=PINECONE_KEY) if PINECONE_KEY else None

if PINECONE_KEY and UPLOAD:
    try:
        index = pc.Index(PINECONE_INDEX)
        print(f"✅ Connected to Pinecone index: {PINECONE_INDEX}")
    except Exception as e:
        print(f"⚠️ Pinecone connection failed: {e}")
        UPLOAD = False


# === HELPERS ===

def clean_text(text: str):
    lines = []
    seen = set()
    for line in text.splitlines():
        norm = line.strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            lines.append(line.strip())
    return "\n".join(lines)


def get_transcripts():
    all_files = []
    for src in SOURCE_DIRS:
        base = Path(src)
        if base.exists():
            for txt in base.rglob("*.txt"):
                all_files.append(txt)
    return all_files


# === MAIN ===

def main():
    print("🔍 Scanning all transcript sources...")
    files = get_transcripts()
    print(f"📂 Found {len(files)} transcript files")

    total_words = 0
    episode_count = 0
    titles = set()
    report = []

    for path in tqdm(files, desc="Processing transcripts"):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            cleaned = clean_text(text)
            words = len(cleaned.split())
            total_words += words
            episode_count += 1
            title = path.parent.name
            titles.add(title)

            report.append({
                "file": str(path),
                "title": title,
                "word_count": words,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })

            if UPLOAD and pc:
                try:
                    vector = client.embeddings.create(
                        model="text-embedding-3-large",
                        input=cleaned[:8000]
                    ).data[0].embedding
                    index.upsert(vectors=[{"id": path.stem, "values": vector}])
                except Exception as e:
                    print(f"⚠️ Upload failed for {path}: {e}")

        except Exception as e:
            print(f"⚠️ Error reading {path}: {e}")

    summary = {
        "total_titles": len(titles),
        "total_episodes": episode_count,
        "total_words": total_words,
        "sources": SOURCE_DIRS,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": report}, f, indent=2)

    print("\n📊 === TRANSCRIPT SUMMARY ===")
    print(f"🎙 Podcast Titles: {len(titles)}")
    print(f"📻 Episodes: {episode_count}")
    print(f"🧾 Word Count: {total_words:,}")
    print(f"💾 Report saved to: {REPORT_PATH}")
    print("=============================")


if __name__ == "__main__":
    main()
