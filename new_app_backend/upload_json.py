import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

print("1. Creating app-data bucket...")
resp = requests.post(
    f"{SUPABASE_URL}/storage/v1/bucket",
    headers=HEADERS,
    json={
        "id": "app-data",
        "name": "app-data",
        "public": True,
        "file_size_limit": 52428800,
    }
)
if resp.status_code in (200, 201):
    print("Bucket created!")
else:
    print(f"Bucket status: {resp.status_code} {resp.text}")

print("\n2. Uploading challans_dump.json...")
with open("challans_dump.json", "rb") as f:
    content = f.read()

resp = requests.post(
    f"{SUPABASE_URL}/storage/v1/object/app-data/challans.json",
    headers={
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "x-upsert": "true",
    },
    data=content
)

if resp.status_code in (200, 201):
    print("Successfully uploaded challans.json to Supabase Storage!")
    print(f"Public URL: {SUPABASE_URL}/storage/v1/object/public/app-data/challans.json")
else:
    print(f"Upload failed: {resp.status_code} {resp.text}")
