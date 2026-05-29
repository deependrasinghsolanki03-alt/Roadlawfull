"""
Batch ingest legal PDFs into ChromaDB with correct state_name metadata.
Skips: Manipur, Meghalaya, Odisha, Punjab, Goa, Assam, Arunachal Pradesh
"""
import os, sys, time

# Fix Windows encoding and buffering
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')

from dotenv import load_dotenv
load_dotenv()

from ss2_engine import RAGEngine

# PDF -> (state_name, level) mapping
PDF_MAP = {
    "India.pdf":            ("ALL",                "national"),
    "Andhra Pradesh.pdf":   ("Andhra Pradesh",     "state"),
    "Bihar.PDF":            ("Bihar",              "state"),
    "Chhattisgarh.pdf":     ("Chhattisgarh",       "state"),
    "Gujrat.pdf":           ("Gujarat",            "state"),
    "Haryana.pdf":          ("Haryana",            "state"),
    "Himachal.pdf":         ("Himachal Pradesh",   "state"),
    "jharkhand.pdf":        ("Jharkhand",          "state"),
    "Karnataka.pdf":        ("Karnataka",          "state"),
    "kerala.pdf":           ("Kerala",             "state"),
    "Madhya Pradesh.pdf":   ("Madhya Pradesh",     "state"),
    "Maharashtra.pdf":      ("Maharashtra",        "state"),
    "Mizoram.pdf":          ("Mizoram",            "state"),
    "nagaland.pdf":         ("Nagaland",           "state"),
    "Rajasthan.pdf":        ("Rajasthan",          "state"),
    "Sikkim.pdf":           ("Sikkim",             "state"),
    "tamil nadu.pdf":       ("Tamil Nadu",         "state"),
    "telangana.pdf":        ("Telangana",          "state"),
    "up.pdf":               ("Uttar Pradesh",      "state"),
    "west bengal.pdf":      ("West Bengal",        "state"),
}

SKIP_FILES = {
    "Manipur.pdf", "meghalaya.pdf", "odisha.pdf", "Punjab.pdf",
    "Goa.pdf", "Assam.pdf", "ARUNACHAL PRADESH.pdf",
}

PDF_DIR = os.path.join(os.path.dirname(__file__), "legal_pdfs")

def main():
    print("=" * 60)
    print("  BATCH INGEST -- Legal PDFs into ChromaDB")
    print("=" * 60)

    engine = RAGEngine()

    total = 0
    skipped = 0
    errors = []

    for filename, (state_name, level) in PDF_MAP.items():
        pdf_path = os.path.join(PDF_DIR, filename)

        if not os.path.exists(pdf_path):
            found = False
            for f in os.listdir(PDF_DIR):
                if f.lower() == filename.lower():
                    pdf_path = os.path.join(PDF_DIR, f)
                    found = True
                    break
            if not found:
                print(f"\n  [SKIP - not found]: {filename}")
                skipped += 1
                continue

        if filename in SKIP_FILES or any(s.lower() == filename.lower() for s in SKIP_FILES):
            print(f"\n  [SKIP - excluded]: {filename}")
            skipped += 1
            continue

        print(f"\n" + "-" * 60)
        print(f"  Ingesting: {filename}")
        print(f"  State: {state_name} | Level: {level}")
        print("-" * 60)

        try:
            start = time.time()
            stats = engine.ingest_pdf(
                pdf_path=pdf_path,
                country="India",
                level=level,
                state_name=state_name,
                start_page=1,
                chunk_size=1200,
            )
            elapsed = time.time() - start
            print(f"  [OK] Done in {elapsed:.1f}s -- {stats.get('chunks_stored', '?')} chunks stored")
            total += 1
        except Exception as e:
            print(f"  [ERROR]: {e}")
            errors.append((filename, str(e)))

    print(f"\n" + "=" * 60)
    print(f"  SUMMARY")
    print(f"  Ingested: {total} PDFs")
    print(f"  Skipped:  {skipped}")
    print(f"  Errors:   {len(errors)}")
    if errors:
        for fn, err in errors:
            print(f"     - {fn}: {err}")
    print("=" * 60)

if __name__ == "__main__":
    main()
