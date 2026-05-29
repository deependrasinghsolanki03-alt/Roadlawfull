import os
import requests
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
BUCKET_NAME = "legal-pdfs"

SUPA_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}

PDF_DIR = os.path.join(os.path.dirname(__file__), "legal_pdfs")

print(f"Registering PDFs in Supabase table 'legal_pdfs'...")

for filename in os.listdir(PDF_DIR):
    if filename.lower().endswith('.pdf'):
        file_path = os.path.join(PDF_DIR, filename)
        file_size = os.path.getsize(file_path)
        
        display_name = filename.replace(".pdf", "").replace(".PDF", "").title()
        
        state_name = "ALL"
        if display_name.lower() != "india":
            state_name = display_name
            
        storage_path = filename # I uploaded directly to root in previous script
        
        # URL encode filename for file_url
        safe_filename = urllib.parse.quote(filename)
        file_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{safe_filename}"
        
        meta_url = f"{SUPABASE_URL}/rest/v1/legal_pdfs"
        
        payload = {
            "filename": filename,
            "display_name": display_name,
            "category": "State Law" if state_name != "ALL" else "National Law",
            "state_name": state_name,
            "country": "India",
            "storage_path": storage_path,
            "file_url": file_url
        }
        
        # Check if already exists
        check_url = f"{meta_url}?filename=eq.{urllib.parse.quote(filename)}"
        check_res = requests.get(check_url, headers=SUPA_HEADERS)
        if check_res.status_code == 200 and len(check_res.json()) > 0:
            print(f"[-] Already registered: {filename}")
            continue
            
        meta_resp = requests.post(meta_url, headers={**SUPA_HEADERS, "Prefer": "return=representation"}, json=payload)
        
        if meta_resp.status_code in [200, 201]:
            print(f"[OK] Registered metadata for {filename}")
        else:
            print(f"[ERROR] Failed to register metadata for {filename}: {meta_resp.text}")

print(f"\nDone registering metadata.")
