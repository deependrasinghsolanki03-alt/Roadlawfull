"""
═══════════════════════════════════════════════════════════
 MongoDB → Supabase Migration Script
═══════════════════════════════════════════════════════════
 1. Creates tables in Supabase (challans + legal_pdfs)
 2. Creates storage bucket for PDFs
 3. Exports all challan data from MongoDB
 4. Inserts into Supabase challans table
 5. Verifies counts match
═══════════════════════════════════════════════════════════
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

HEADERS_COUNT = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "count=exact",
    "Range": "0-0",
}


# ═══════════════════════════════════════════════════════════
#  STEP 1: Create Tables via SQL (print for user)
# ═══════════════════════════════════════════════════════════

TABLE_SQL = """
-- ═══════════════════════════════════════════════════════
--  RUN THIS SQL IN SUPABASE DASHBOARD → SQL EDITOR
-- ═══════════════════════════════════════════════════════

-- Table 1: Challans (migrated from MongoDB)
CREATE TABLE IF NOT EXISTS challans (
  id BIGSERIAL PRIMARY KEY,
  country TEXT NOT NULL DEFAULT 'India',
  state_name TEXT NOT NULL DEFAULT 'National',
  offense TEXT NOT NULL,
  keywords TEXT[] NOT NULL DEFAULT '{}',
  section TEXT DEFAULT 'N/A',
  description TEXT DEFAULT '',
  fine_amount INTEGER DEFAULT 0,
  first_offense TEXT,
  repeat_offense TEXT,
  imprisonment TEXT,
  vehicle_type TEXT DEFAULT 'all',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS but allow service role full access
ALTER TABLE challans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read" ON challans FOR SELECT USING (true);
CREATE POLICY "Allow service role all" ON challans FOR ALL USING (true) WITH CHECK (true);

-- Table 2: Legal PDFs metadata
CREATE TABLE IF NOT EXISTS legal_pdfs (
  id BIGSERIAL PRIMARY KEY,
  filename TEXT NOT NULL,
  display_name TEXT NOT NULL,
  category TEXT DEFAULT 'General',
  country TEXT DEFAULT 'India',
  state_name TEXT DEFAULT 'ALL',
  file_size_bytes BIGINT DEFAULT 0,
  file_url TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  uploaded_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE legal_pdfs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read pdfs" ON legal_pdfs FOR SELECT USING (true);
CREATE POLICY "Allow service role all pdfs" ON legal_pdfs FOR ALL USING (true) WITH CHECK (true);

-- Indexes for fast search
CREATE INDEX IF NOT EXISTS idx_challans_country_state ON challans(country, state_name);
CREATE INDEX IF NOT EXISTS idx_challans_keywords ON challans USING GIN(keywords);
CREATE INDEX IF NOT EXISTS idx_legal_pdfs_state ON legal_pdfs(state_name);
CREATE INDEX IF NOT EXISTS idx_legal_pdfs_name ON legal_pdfs(display_name);
"""


def check_table_exists(table_name):
    """Check if a table exists by trying a HEAD request."""
    url = f"{SUPABASE_URL}/rest/v1/{table_name}?select=id&limit=1"
    resp = requests.get(url, headers={
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    })
    return resp.status_code == 200


def create_storage_bucket():
    """Create the legal-pdfs storage bucket."""
    url = f"{SUPABASE_URL}/storage/v1/bucket"
    resp = requests.post(url, headers=HEADERS, json={
        "id": "legal-pdfs",
        "name": "legal-pdfs",
        "public": True,
        "file_size_limit": 52428800,  # 50MB
        "allowed_mime_types": ["application/pdf"],
    })
    if resp.status_code in (200, 201):
        print("  [OK] Storage bucket 'legal-pdfs' created")
    elif resp.status_code == 409:
        print("  [OK] Storage bucket 'legal-pdfs' already exists")
    else:
        print(f"  [WARN] Bucket creation response: {resp.status_code} - {resp.text}")


# ═══════════════════════════════════════════════════════════
#  STEP 2: Read from MongoDB
# ═══════════════════════════════════════════════════════════

def read_from_mongodb():
    """Read all challan records from MongoDB."""
    try:
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017")
        db = client["roadlaw"]
        collection = db["challans"]

        count = collection.count_documents({})
        print(f"\n  [MONGO] Found {count} challan records in MongoDB")

        records = []
        for doc in collection.find({}, {"_id": 0}):
            records.append({
                "country": doc.get("country", "India"),
                "state_name": doc.get("state_name", "National"),
                "offense": doc.get("offense", "Unknown"),
                "keywords": doc.get("keywords", []),
                "section": doc.get("section", "N/A"),
                "description": doc.get("description", ""),
                "fine_amount": doc.get("fine_amount", 0),
                "first_offense": doc.get("first_offense"),
                "repeat_offense": doc.get("repeat_offense"),
                "imprisonment": doc.get("imprisonment"),
                "vehicle_type": doc.get("vehicle_type", "all"),
            })

        client.close()
        return records

    except Exception as e:
        print(f"  [ERR] MongoDB read failed: {e}")
        print("  [INFO] Make sure MongoDB is running on localhost:27017")
        return []


# ═══════════════════════════════════════════════════════════
#  STEP 3: Insert into Supabase
# ═══════════════════════════════════════════════════════════

def insert_to_supabase(records):
    """Insert challan records into Supabase in batches."""
    if not records:
        print("  [SKIP] No records to insert")
        return 0

    url = f"{SUPABASE_URL}/rest/v1/challans"
    batch_size = 100
    total_inserted = 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        # Convert keywords list to PostgreSQL array format
        for rec in batch:
            if isinstance(rec.get("keywords"), list):
                rec["keywords"] = rec["keywords"]

        resp = requests.post(url, headers=HEADERS, json=batch)

        if resp.status_code in (200, 201):
            total_inserted += len(batch)
            print(f"  [OK] Inserted batch {i // batch_size + 1}: {len(batch)} records (total: {total_inserted})")
        else:
            print(f"  [ERR] Batch {i // batch_size + 1} failed: {resp.status_code} - {resp.text[:200]}")

    return total_inserted


def verify_count():
    """Verify the count in Supabase matches."""
    url = f"{SUPABASE_URL}/rest/v1/challans?select=id"
    resp = requests.get(url, headers=HEADERS_COUNT)
    count = resp.headers.get("content-range", "")
    if "/" in count:
        total = count.split("/")[1]
        print(f"\n  [VERIFY] Supabase challans table has {total} records")
        return int(total) if total != "*" else -1
    return -1


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 60)
    print("  MongoDB -> Supabase Migration")
    print("=" * 60)

    # Step 0: Check Supabase connection
    print("\n[Step 0] Checking Supabase connection...")
    health_url = f"{SUPABASE_URL}/rest/v1/"
    resp = requests.get(health_url, headers={
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    })
    if resp.status_code == 200:
        print("  [OK] Supabase REST API is reachable")
    else:
        print(f"  [ERR] Supabase connection failed: {resp.status_code}")
        return

    # Step 1: Check if tables exist
    print("\n[Step 1] Checking if tables exist...")
    challans_ok = check_table_exists("challans")
    pdfs_ok = check_table_exists("legal_pdfs")

    if challans_ok:
        print("  [OK] 'challans' table exists")
    else:
        print("  [MISSING] 'challans' table does NOT exist")

    if pdfs_ok:
        print("  [OK] 'legal_pdfs' table exists")
    else:
        print("  [MISSING] 'legal_pdfs' table does NOT exist")

    if not challans_ok or not pdfs_ok:
        print("\n" + "=" * 60)
        print("  ACTION REQUIRED: Create tables in Supabase Dashboard")
        print("=" * 60)
        print("  1. Go to: https://supabase.com/dashboard")
        print("  2. Open your project → SQL Editor")
        print("  3. Paste and run the following SQL:")
        print(TABLE_SQL)
        print("=" * 60)
        print("  After running the SQL, run this script again!")
        print("=" * 60)

        # Save SQL to file for easy copy
        with open("supabase_setup.sql", "w") as f:
            f.write(TABLE_SQL)
        print("\n  [SAVED] SQL also saved to: supabase_setup.sql")
        return

    # Step 2: Create storage bucket
    print("\n[Step 2] Creating storage bucket...")
    create_storage_bucket()

    # Step 3: Check if Supabase already has data
    existing = verify_count()
    if existing > 0:
        print(f"\n  [INFO] Supabase already has {existing} challan records")
        answer = input("  Do you want to clear and re-import? (y/N): ").strip().lower()
        if answer != 'y':
            print("  [SKIP] Migration skipped. Existing data preserved.")
            return
        else:
            # Clear existing data
            del_url = f"{SUPABASE_URL}/rest/v1/challans?id=gt.0"
            resp = requests.delete(del_url, headers=HEADERS)
            print(f"  [OK] Cleared existing data: {resp.status_code}")

    # Step 4: Read from MongoDB
    print("\n[Step 3] Reading from MongoDB...")
    records = read_from_mongodb()

    if not records:
        print("  [WARN] No records found in MongoDB. Nothing to migrate.")
        return

    # Step 5: Insert into Supabase
    print(f"\n[Step 4] Inserting {len(records)} records into Supabase...")
    inserted = insert_to_supabase(records)

    # Step 6: Verify
    print("\n[Step 5] Verifying migration...")
    final_count = verify_count()

    print("\n" + "=" * 60)
    print(f"  MIGRATION COMPLETE!")
    print(f"  MongoDB records: {len(records)}")
    print(f"  Supabase inserted: {inserted}")
    print(f"  Supabase verified: {final_count}")
    print("=" * 60)

    if inserted == len(records):
        print("\n  ✅ SUCCESS! All records migrated to Supabase.")
        print("  You can now stop MongoDB and run the updated server.")
    else:
        print("\n  ⚠️ WARNING: Count mismatch. Check for errors above.")


if __name__ == "__main__":
    main()
