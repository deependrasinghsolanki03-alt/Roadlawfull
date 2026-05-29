"""
===================================================================
 Smart Challan Calculator -- server.py
===================================================================
 In-Memory Folder Routing with MongoDB + Hot-Reload

 Architecture:
   - MongoDB stores all challan data (db: roadlaw, collection: challans)
   - /data/{Country}/National/challans.json   (source files for import)
   - /data/{Country}/{State_Name}/challans.json
   - All data loaded from MongoDB into memory_db dict on startup
   - Groq LLM extracts offense keywords from natural language
   - State > National fallback for conflict resolution

 Endpoints:
   POST /api/calculator                -- Smart challan lookup
   POST /api/admin/reload              -- Hot-reload from MongoDB to RAM
   POST /api/admin/import-json         -- Import JSON files from /data into MongoDB
   POST /api/admin/add-challan         -- Add a single challan to MongoDB
   DELETE /api/admin/clear-challans    -- Clear all challan data from MongoDB
   GET  /api/calculator/health         -- Health check
   GET  /api/calculator/stats          -- Memory DB stats
===================================================================
"""

import os
import json
import time
import traceback
from pathlib import Path
from typing import Optional, List

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "roadlaw")


# ===================================================================
#  FastAPI App
# ===================================================================

app = FastAPI(
    title="Smart Challan Calculator API",
    description="In-Memory Folder Routing with MongoDB + NLP-powered offense extraction",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================================================================
#  MONGODB CONNECTION
# ===================================================================

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
challans_collection = db["challans"]

print(f"\n  [MONGO] Connected to {MONGO_URI} / {MONGO_DB}")


# ===================================================================
#  STATE ALIASES (abbreviation -> full name)
# ===================================================================

STATE_ALIASES = {
    # India
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
}


def normalize_state(state_name: str) -> str:
    """Normalize state input: 'mp' -> 'Madhya Pradesh', 'MP' -> 'Madhya Pradesh'."""
    if not state_name or state_name.strip() == "":
        return state_name
    key = state_name.strip().lower()
    return STATE_ALIASES.get(key, state_name.strip().title())


# ===================================================================
#  GLOBAL IN-MEMORY CACHE (loaded from MongoDB)
# ===================================================================

# Structure: memory_db["India"]["Madhya Pradesh"] = [ {...}, {...} ]
#            memory_db["India"]["National"]        = [ {...}, {...} ]
memory_db: dict = {}

DATA_DIR = Path("./data")


async def load_from_mongo():
    """
    Clear memory_db and reload all challan data from MongoDB into RAM.
    Groups by country + state_name for fast in-memory lookup.
    """
    global memory_db
    memory_db.clear()

    total = 0
    cursor = challans_collection.find({}, {"_id": 0})

    for doc in cursor:
        country = doc.get("country", "India")
        state = doc.get("state_name", "National")

        if country not in memory_db:
            memory_db[country] = {}
        if state not in memory_db[country]:
            memory_db[country][state] = []

        memory_db[country][state].append(doc)
        total += 1

    # Print summary
    for country, states in memory_db.items():
        for state, records in states.items():
            print(f"  [OK] {len(records):>4} challans -- {country}/{state}")

    print(f"\n  [STATS] Total: {total} challan records loaded from MongoDB\n")
    return total


async def import_json_to_mongo():
    """
    Read JSON files from /data/{Country}/{State}/challans.json
    and insert them into MongoDB. Each record gets country + state_name metadata.
    """
    if not DATA_DIR.exists():
        print("  [WARN] /data directory not found")
        return 0

    total_imported = 0

    for country_dir in sorted(DATA_DIR.iterdir()):
        if not country_dir.is_dir():
            continue

        country_name = country_dir.name  # e.g. "India"

        for state_dir in sorted(country_dir.iterdir()):
            if not state_dir.is_dir():
                continue

            state_name = state_dir.name  # e.g. "Madhya Pradesh" or "National"
            challan_file = state_dir / "challans.json"

            if challan_file.exists():
                try:
                    with open(challan_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Support both list and dict-with-list formats
                    if isinstance(data, list):
                        records = data
                    elif isinstance(data, dict) and "challans" in data:
                        records = data["challans"]
                    else:
                        print(f"  [WARN] Unexpected format in {challan_file}")
                        continue

                    # Add country + state_name to each record
                    for rec in records:
                        rec["country"] = country_name
                        rec["state_name"] = state_name

                    # Remove existing records for this country/state to avoid duplicates
                    challans_collection.delete_many({
                        "country": country_name,
                        "state_name": state_name,
                    })

                    # Insert into MongoDB
                    if records:
                        challans_collection.insert_many(records)
                        total_imported += len(records)
                        print(f"  [OK] Imported {len(records):>4} challans -- {country_name}/{state_name}")

                except json.JSONDecodeError as e:
                    print(f"  [ERR] JSON parse error in {challan_file}: {e}")
                except Exception as e:
                    print(f"  [ERR] Error importing {challan_file}: {e}")

    print(f"\n  [STATS] Total: {total_imported} records imported to MongoDB\n")
    return total_imported


# ===================================================================
#  GROQ LLM -- Offense Keyword Extractor
# ===================================================================

from langchain_groq import ChatGroq

llm = ChatGroq(
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

Examples:
- "bina helmet fine" -> no_helmet
- "drunk driving penalty MP" -> drunk_driving
- "phone use while driving fine" -> using_phone
- "signal jump aur helmet nahi" -> red_light_jump, no_helmet
- "tez speed se gaadi chalana" -> over_speeding

User Query: {query}

Extracted keyword(s):"""


def extract_offense_keywords(query: str) -> list[str]:
    """Use Groq LLM to extract offense keywords from natural language."""
    try:
        response = llm.invoke(EXTRACT_PROMPT.format(query=query))
        raw = response.content.strip().lower()

        # Clean up any extra text
        raw = raw.replace(".", "").replace("\"", "").replace("'", "")

        # Split by comma
        keywords = [k.strip() for k in raw.split(",") if k.strip()]

        print(f"  [AI] LLM extracted: {keywords}")
        return keywords

    except Exception as e:
        print(f"  [ERR] LLM extraction error: {e}")
        return [query.strip().lower()]


# ===================================================================
#  SEARCH ENGINE -- In-Memory Lookup with Fallback
# ===================================================================

def search_challans(keywords: list[str], country: str, state_name: str) -> dict:
    """
    Search memory_db for matching challans.
    Priority: State > National (fallback)
    """

    country_data = memory_db.get(country, {})
    if not country_data:
        return {
            "found": False,
            "message": f"No challan data available for country: {country}",
            "results": [],
            "national_comparison": [],
            "total_fine": 0,
            "currency": "INR",
            "breakdown": {"state_matches": 0, "national_fallbacks": 0, "national_comparisons": 0},
        }

    # -- Step 1: Search in State data --
    state_results = []
    state_data = country_data.get(state_name, [])

    for keyword in keywords:
        for challan in state_data:
            challan_keywords = [k.lower() for k in challan.get("keywords", [])]
            if keyword in challan_keywords:
                state_results.append({
                    **{k: v for k, v in challan.items() if k not in ("country", "state_name")},
                    "matched_keyword": keyword,
                    "source_jurisdiction": state_name,
                    "priority": "STATE",
                })

    # -- Step 2: National fallback for unmatched keywords --
    national_results = []
    matched_state_keywords = {r["matched_keyword"] for r in state_results}
    unmatched_keywords = [k for k in keywords if k not in matched_state_keywords]

    national_data = country_data.get("National", [])

    for keyword in unmatched_keywords:
        for challan in national_data:
            challan_keywords = [k.lower() for k in challan.get("keywords", [])]
            if keyword in challan_keywords:
                national_results.append({
                    **{k: v for k, v in challan.items() if k not in ("country", "state_name")},
                    "matched_keyword": keyword,
                    "source_jurisdiction": "National",
                    "priority": "NATIONAL (fallback)",
                })

    # -- National comparison for state-matched keywords --
    national_comparison = []
    for keyword in matched_state_keywords:
        for challan in national_data:
            challan_keywords = [k.lower() for k in challan.get("keywords", [])]
            if keyword in challan_keywords:
                national_comparison.append({
                    **{k: v for k, v in challan.items() if k not in ("country", "state_name")},
                    "matched_keyword": keyword,
                    "source_jurisdiction": "National",
                    "priority": "NATIONAL (comparison)",
                })

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
#  REQUEST / RESPONSE MODELS
# ===================================================================

class CalculatorRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Natural language query e.g. 'bina helmet fine'")
    country: str = Field(default="India")
    state_name: str = Field(default="Madhya Pradesh", description="e.g. Madhya Pradesh, Maharashtra")


class AddChallanRequest(BaseModel):
    country: str = Field(default="India")
    state_name: str = Field(default="National", description="State name or 'National'")
    offense: str = Field(..., min_length=3)
    keywords: List[str] = Field(..., min_length=1)
    section: str = Field(default="N/A")
    description: str = Field(default="")
    fine_amount: int = Field(default=0)
    first_offense: Optional[str] = None
    repeat_offense: Optional[str] = None
    imprisonment: Optional[str] = None


def api_success(data: dict):
    return JSONResponse(content={"success": True, "data": data})


def api_error(status: int, code: str, message: str):
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


# ===================================================================
#  STARTUP -- Load data from MongoDB into RAM
# ===================================================================

@app.on_event("startup")
async def startup():
    print("\n" + "=" * 60)
    print("  CHALLAN CALCULATOR -- Loading data from MongoDB")
    print("=" * 60 + "\n")

    # Check if MongoDB has data
    count = challans_collection.count_documents({})

    if count == 0:
        print("  [INFO] MongoDB is empty. Auto-importing from /data JSON files...\n")
        await import_json_to_mongo()

    total = await load_from_mongo()
    print(f"  [START] Server ready -- {total} challans in memory\n")


# ===================================================================
#  POST /api/calculator -- Smart Challan Lookup
# ===================================================================

@app.post("/api/calculator")
async def calculator(req: CalculatorRequest):
    start = time.time()

    try:
        # Normalize state: "mp" -> "Madhya Pradesh", "UP" -> "Uttar Pradesh"
        resolved_state = normalize_state(req.state_name)

        print(f"\n{'='*60}")
        print(f"  CHALLAN: \"{req.query}\" | {req.country} / {req.state_name} -> {resolved_state}")
        print(f"{'='*60}")

        keywords = extract_offense_keywords(req.query)

        if not keywords:
            return api_error(400, "NO_KEYWORDS", "Could not extract offense from query")

        result = search_challans(keywords, req.country, resolved_state)

        elapsed = int((time.time() - start) * 1000)

        response_data = {
            "query": req.query,
            "extracted_keywords": keywords,
            "country": req.country,
            "state_name": req.state_name,
            "found": result["found"],
            "total_fine": result["total_fine"],
            "currency": result["currency"],
            "violations": [],
            "national_comparison": [],
            "breakdown": result["breakdown"],
            "response_time_ms": elapsed,
        }

        for r in result["results"]:
            response_data["violations"].append({
                "offense": r.get("offense", r.get("title", "Unknown")),
                "fine_amount": r.get("fine_amount", 0),
                "section": r.get("section", "N/A"),
                "description": r.get("description", ""),
                "first_offense": r.get("first_offense", None),
                "repeat_offense": r.get("repeat_offense", None),
                "imprisonment": r.get("imprisonment", None),
                "source_jurisdiction": r.get("source_jurisdiction", "Unknown"),
                "priority": r.get("priority", ""),
                "matched_keyword": r.get("matched_keyword", ""),
            })

        for r in result["national_comparison"]:
            response_data["national_comparison"].append({
                "offense": r.get("offense", r.get("title", "Unknown")),
                "fine_amount": r.get("fine_amount", 0),
                "section": r.get("section", "N/A"),
                "note": f"National law fine: Rs.{r.get('fine_amount', 0)} (vs State applied)",
            })

        if not result["found"]:
            response_data["message"] = "No matching challan found for the given offense."

        print(f"  [OK] Found {len(result['results'])} violations, total fine: Rs.{result['total_fine']}")
        print(f"  [{elapsed}ms]\n{'='*60}\n")

        return api_success(response_data)

    except Exception as e:
        traceback.print_exc()
        return api_error(500, "CALCULATOR_ERROR", str(e))


# ===================================================================
#  POST /api/admin/reload -- Hot Reload from MongoDB to RAM
# ===================================================================

@app.post("/api/admin/reload")
async def reload_data():
    try:
        print("\n  [RELOAD] Hot-reloading challan data from MongoDB...\n")
        total = await load_from_mongo()
        return api_success({
            "status": "success",
            "message": "Memory DB reloaded from MongoDB",
            "total_records": total,
            "countries": list(memory_db.keys()),
            "structure": {
                country: {state: len(records) for state, records in states.items()}
                for country, states in memory_db.items()
            },
        })
    except Exception as e:
        traceback.print_exc()
        return api_error(500, "RELOAD_ERROR", str(e))


# ===================================================================
#  POST /api/admin/import-json -- Import JSON files into MongoDB
# ===================================================================

@app.post("/api/admin/import-json")
async def import_json():
    """Import challan data from /data JSON files into MongoDB."""
    try:
        print("\n  [IMPORT] Importing JSON files into MongoDB...\n")
        total = await import_json_to_mongo()

        # Reload memory after import
        await load_from_mongo()

        return api_success({
            "status": "success",
            "message": f"Imported {total} records from JSON files into MongoDB",
            "total_imported": total,
            "structure": {
                country: {state: len(records) for state, records in states.items()}
                for country, states in memory_db.items()
            },
        })
    except Exception as e:
        traceback.print_exc()
        return api_error(500, "IMPORT_ERROR", str(e))


# ===================================================================
#  POST /api/admin/add-challan -- Add a single challan to MongoDB
# ===================================================================

@app.post("/api/admin/add-challan")
async def add_challan(req: AddChallanRequest):
    """Add a single challan record to MongoDB."""
    try:
        doc = {
            "country": req.country,
            "state_name": req.state_name,
            "offense": req.offense,
            "keywords": req.keywords,
            "section": req.section,
            "description": req.description,
            "fine_amount": req.fine_amount,
            "first_offense": req.first_offense,
            "repeat_offense": req.repeat_offense,
            "imprisonment": req.imprisonment,
        }

        challans_collection.insert_one(doc)

        # Reload memory
        await load_from_mongo()

        return api_success({
            "status": "success",
            "message": f"Added challan: {req.offense} ({req.country}/{req.state_name})",
            "record": {k: v for k, v in doc.items() if k != "_id"},
        })
    except Exception as e:
        traceback.print_exc()
        return api_error(500, "ADD_ERROR", str(e))


# ===================================================================
#  DELETE /api/admin/clear-challans -- Clear all challan data
# ===================================================================

@app.delete("/api/admin/clear-challans")
async def clear_challans():
    """Delete ALL challan data from MongoDB and memory."""
    try:
        result = challans_collection.delete_many({})
        memory_db.clear()

        return api_success({
            "status": "success",
            "message": f"Deleted {result.deleted_count} records from MongoDB",
            "deleted_count": result.deleted_count,
        })
    except Exception as e:
        traceback.print_exc()
        return api_error(500, "CLEAR_ERROR", str(e))


# ===================================================================
#  GET /api/calculator/health
# ===================================================================

@app.get("/api/calculator/health")
async def health():
    try:
        mongo_ok = mongo_client.admin.command("ping").get("ok", 0) == 1
    except Exception:
        mongo_ok = False

    return api_success({
        "server": "ok",
        "engine": "In-Memory + MongoDB + Groq LLM",
        "mongodb": "connected" if mongo_ok else "disconnected",
        "data_loaded": len(memory_db) > 0,
        "countries": list(memory_db.keys()),
    })


# ===================================================================
#  GET /api/sync-challans -- Dump ALL challans for offline mode (Android)
# ===================================================================

@app.get("/api/sync-challans")
async def sync_challans():
    """
    Returns a flat JSON array of every challan record for the Android app
    to download and store in its local Room Database (offline mode).
    
    Each object has fields matching the Android ChallanEntity:
      state, offense_id, violation, law_section, fine_amount,
      imprisonment, description, vehicle_type, keywords
    """
    all_challans = []

    for country, states in memory_db.items():
        for state_name, records in states.items():
            for rec in records:
                all_challans.append({
                    "state": state_name if state_name != "National" else "ALL",
                    "offense_id": rec.get("offense", "").lower().replace(" ", "_"),
                    "violation": rec.get("offense", ""),
                    "law_section": rec.get("section", "N/A"),
                    "fine_amount": rec.get("fine_amount", 0),
                    "imprisonment": rec.get("imprisonment", None),
                    "description": rec.get("description", ""),
                    "vehicle_type": rec.get("vehicle_type", "all"),
                    "keywords": rec.get("keywords", []),
                })

    return JSONResponse(content=all_challans)


# ===================================================================
#  GET /api/calculator/stats -- Memory DB Stats
# ===================================================================

@app.get("/api/calculator/stats")
async def stats():
    structure = {}
    total = 0
    for country, states in memory_db.items():
        structure[country] = {}
        for state, records in states.items():
            structure[country][state] = len(records)
            total += len(records)

    mongo_count = challans_collection.count_documents({})

    return api_success({
        "total_in_memory": total,
        "total_in_mongodb": mongo_count,
        "countries": len(memory_db),
        "structure": structure,
    })


# ===================================================================
#  RUN
# ===================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Smart Challan Calculator -- port 3001")
    print("=" * 60 + "\n")

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=3001,
        reload=False,
        log_level="info",
    )
