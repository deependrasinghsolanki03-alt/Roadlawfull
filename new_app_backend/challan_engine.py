"""
===================================================================
 Challan Engine -- challan_engine.py (Supabase Storage JSON Edition)
===================================================================
 Uses a static JSON file stored in Supabase Storage instead of SQL.
 Perfect for offline-first Android apps!

 Contains:
   - STATE_ALIASES (merged superset)
   - normalize_state()
   - load_from_supabase() -> fetches challans.json
   - add_challan_to_supabase() -> downloads, appends, re-uploads
   - Groq LLM keyword extraction
   - search_challans() in-memory lookup
===================================================================
"""

import os
import json
import time
import requests
from pydantic import BaseModel, Field
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# We now store data in a public bucket called 'app-data'
CHALLAN_JSON_URL = f"{SUPABASE_URL}/storage/v1/object/public/app-data/challans.json"
CHALLAN_UPLOAD_URL = f"{SUPABASE_URL}/storage/v1/object/app-data/challans.json"

SUPA_STORAGE_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

# ===================================================================
#  STATE ALIASES
# ===================================================================

STATE_ALIASES = {
    "mp": "Madhya Pradesh", "madhya pradesh": "Madhya Pradesh",
    "up": "Uttar Pradesh", "uttar pradesh": "Uttar Pradesh",
    "mh": "Maharashtra", "maharashtra": "Maharashtra",
    "ka": "Karnataka", "karnataka": "Karnataka",
    "tn": "Tamil Nadu", "tamil nadu": "Tamil Nadu",
    "ap": "Andhra Pradesh", "andhra pradesh": "Andhra Pradesh",
    "ts": "Telangana", "telangana": "Telangana",
    "rj": "Rajasthan", "rajasthan": "Rajasthan",
    "gj": "Gujarat", "gujarat": "Gujarat",
    "wb": "West Bengal", "west bengal": "West Bengal",
    "dl": "Delhi", "delhi": "Delhi", "new delhi": "Delhi",
    "hr": "Haryana", "haryana": "Haryana",
    "pb": "Punjab", "punjab": "Punjab",
    "br": "Bihar", "bihar": "Bihar",
    "jh": "Jharkhand", "jharkhand": "Jharkhand",
    "cg": "Chhattisgarh", "chhattisgarh": "Chhattisgarh",
    "or": "Odisha", "odisha": "Odisha", "orissa": "Odisha",
    "kl": "Kerala", "kerala": "Kerala",
    "as": "Assam", "assam": "Assam",
    "uk": "Uttarakhand", "uttarakhand": "Uttarakhand",
    "ga": "Goa", "goa": "Goa",
    "hp": "Himachal Pradesh", "himachal pradesh": "Himachal Pradesh",
    "jk": "Jammu and Kashmir", "jammu and kashmir": "Jammu and Kashmir",
    "mn": "Manipur", "manipur": "Manipur",
    "ml": "Meghalaya", "meghalaya": "Meghalaya",
    "mz": "Mizoram", "mizoram": "Mizoram",
    "nl": "Nagaland", "nagaland": "Nagaland",
    "sk": "Sikkim", "sikkim": "Sikkim",
    "tr": "Tripura", "tripura": "Tripura",
    "ar": "Arunachal Pradesh", "arunachal pradesh": "Arunachal Pradesh",
    "arunachal": "Arunachal Pradesh",
    "ca": "California", "california": "California",
    "ny": "New York", "new york": "New York",
    "tx": "Texas", "texas": "Texas",
    "all": "ALL", "national": "ALL",
}

def normalize_state(state_name: str) -> str:
    if not state_name or state_name.strip() == "": return "ALL"
    return STATE_ALIASES.get(state_name.strip().lower(), state_name.strip().title())

# ===================================================================
#  GLOBAL IN-MEMORY CACHE
# ===================================================================

memory_db: dict = {}

# ===================================================================
#  JSON FETCH & UPLOAD (Supabase Storage)
# ===================================================================

async def load_from_supabase():
    """Fetch challans.json from Supabase Storage and build memory_db."""
    global memory_db
    memory_db.clear()
    
    print(f"  [SUPABASE] Fetching JSON from {CHALLAN_JSON_URL}")
    resp = requests.get(CHALLAN_JSON_URL)
    
    if resp.status_code != 200:
        print(f"  [ERR] Failed to download JSON: {resp.status_code}")
        return 0
        
    records = resp.json()
    total = 0
    
    for doc in records:
        country = doc.get("country", "India")
        state = doc.get("state_name", "National")

        if country not in memory_db: memory_db[country] = {}
        if state not in memory_db[country]: memory_db[country][state] = []

        memory_db[country][state].append(doc)
        total += 1

    print(f"  [STATS] Total: {total} challan records loaded from JSON\n")
    return total

async def add_challan_to_supabase(doc: dict):
    """Download current JSON, append record, and upload back."""
    resp = requests.get(CHALLAN_JSON_URL)
    records = resp.json() if resp.status_code == 200 else []
    
    records.append(doc)
    
    # Upload back to storage
    upload_resp = requests.post(
        CHALLAN_UPLOAD_URL,
        headers={**SUPA_STORAGE_HEADERS, "x-upsert": "true"},
        json=records
    )
    if upload_resp.status_code not in (200, 201):
        raise Exception(f"Failed to update JSON in storage: {upload_resp.text}")

async def clear_all_challans():
    """Uploads an empty list to the JSON file."""
    upload_resp = requests.post(
        CHALLAN_UPLOAD_URL,
        headers={**SUPA_STORAGE_HEADERS, "x-upsert": "true"},
        json=[]
    )
    return upload_resp.status_code in (200, 201)

def check_supabase_health():
    try:
        resp = requests.head(CHALLAN_JSON_URL, timeout=5)
        return resp.status_code == 200
    except:
        return False

# ===================================================================
#  GROQ LLM
# ===================================================================

from langchain_groq import ChatGroq

challan_llm = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.3-70b-versatile",
    temperature=0,
)

EXTRACT_PROMPT = """You are a legal keyword extractor for Indian traffic violations.
Given a user's natural language query about a traffic fine or challan, extract the EXACT offense keyword(s) that would match a database lookup.

RULES:
1. Output ONLY the extracted keyword(s), nothing else
2. Use standard offense terms like: no_helmet, no_seatbelt, drunk_driving, over_speeding, red_light_jump, no_license, no_insurance, using_phone, wrong_side, no_parking, triple_riding, no_registration, no_puc, overloading, dangerous_driving, juvenile_driving
3. If multiple offenses are mentioned, separate with comma
4. Convert Hindi/colloquial terms to standard English keywords
5. NO explanation, NO sentences -- just the keyword(s)

User Query: {query}
Extracted keyword(s):"""

def extract_offense_keywords(query: str) -> list[str]:
    try:
        response = challan_llm.invoke(EXTRACT_PROMPT.format(query=query))
        raw = response.content.strip().lower()
        raw = raw.replace(".", "").replace("\"", "").replace("'", "")
        keywords = [k.strip() for k in raw.split(",") if k.strip()]
        return keywords
    except Exception as e:
        print(f"  [ERR] LLM extraction error: {e}")
        return [query.strip().lower()]

# ===================================================================
#  SEARCH ENGINE
# ===================================================================

def search_challans(keywords: list[str], country: str, state_name: str) -> dict:
    country_data = memory_db.get(country, {})
    if not country_data:
        return {
            "found": False, "message": f"No data for {country}",
            "results": [], "national_comparison": [], "total_fine": 0, "currency": "INR",
            "breakdown": {"state_matches": 0, "national_fallbacks": 0, "national_comparisons": 0},
        }

    state_results = []
    state_data = country_data.get(state_name, [])

    for keyword in keywords:
        for challan in state_data:
            c_keywords = [k.lower() for k in challan.get("keywords", [])]
            if keyword in c_keywords:
                state_results.append({**challan, "matched_keyword": keyword, "source_jurisdiction": state_name, "priority": "STATE"})

    national_results = []
    matched_state_keywords = {r["matched_keyword"] for r in state_results}
    unmatched_keywords = [k for k in keywords if k not in matched_state_keywords]
    national_data = country_data.get("National", [])

    for keyword in unmatched_keywords:
        for challan in national_data:
            c_keywords = [k.lower() for k in challan.get("keywords", [])]
            if keyword in c_keywords:
                national_results.append({**challan, "matched_keyword": keyword, "source_jurisdiction": "National", "priority": "NATIONAL (fallback)"})

    national_comparison = []
    for keyword in matched_state_keywords:
        for challan in national_data:
            c_keywords = [k.lower() for k in challan.get("keywords", [])]
            if keyword in c_keywords:
                national_comparison.append({**challan, "matched_keyword": keyword, "source_jurisdiction": "National", "priority": "NATIONAL (comparison)"})

    all_results = state_results + national_results
    total_fine = sum(r.get("fine_amount", 0) for r in all_results)

    return {
        "found": len(all_results) > 0,
        "results": all_results,
        "national_comparison": national_comparison,
        "total_fine": total_fine,
        "currency": "INR" if country == "India" else "USD",
        "breakdown": {
            "state_matches": len(state_results),
            "national_fallbacks": len(national_results),
            "national_comparisons": len(national_comparison),
        },
    }

# ===================================================================
#  MODELS
# ===================================================================

class CalculatorRequest(BaseModel):
    query: str = Field(...)
    country: str = Field(default="India")
    state_name: str = Field(default="Madhya Pradesh")

class AddChallanRequest(BaseModel):
    country: str = Field(default="India")
    state_name: str = Field(default="National")
    offense: str = Field(...)
    keywords: List[str] = Field(...)
    section: str = Field(default="N/A")
    description: str = Field(default="")
    fine_amount: int = Field(default=0)
    first_offense: Optional[str] = None
    repeat_offense: Optional[str] = None
    imprisonment: Optional[str] = None
