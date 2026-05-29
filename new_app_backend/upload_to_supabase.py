import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
BUCKET_NAME = "legal-pdfs"

headers = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/pdf"
}

PDF_DIR = os.path.join(os.path.dirname(__file__), "legal_pdfs")

print(f"Uploading PDFs from {PDF_DIR} to Supabase bucket '{BUCKET_NAME}'...")

count = 0
for filename in os.listdir(PDF_DIR):
    if filename.lower().endswith('.pdf'):
        file_path = os.path.join(PDF_DIR, filename)
        
        with open(file_path, "rb") as f:
            pdf_data = f.read()
            
        url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET_NAME}/{filename}"
        
        # Check if exists (upsert)
        res = requests.post(url, headers=headers, data=pdf_data)
        
        if res.status_code in [200, 201]:
            print(f"[OK] Uploaded {filename}")
            count += 1
        elif res.status_code == 400 and 'already exists' in res.text.lower():
            # Already exists, try PUT to overwrite or just skip
            print(f"[-] Already exists: {filename}")
        else:
            print(f"[ERROR] Failed to upload {filename}: {res.status_code} - {res.text}")

print(f"\nDone! Successfully uploaded {count} PDFs.")
