"""
=====================================================================
 Unified FastAPI Server -- server.py (Supabase Edition)
=====================================================================
 Merged: AI Legal Assistant + Smart Challan Calculator + Legal PDFs
 Single server on port 3000.
 Database: Supabase (PostgreSQL + Storage) -- NO MongoDB

 AI Legal Endpoints:
   POST /api/search          -- Hierarchy-aware RAG search
   POST /api/admin/ingest    -- Upload PDF with country/level metadata
   POST /api/admin/ingest-local -- Ingest server PDF with metadata
   GET  /api/admin/pdfs      -- List server PDFs
   GET  /api/health          -- Health check
   GET  /api/admin/health    -- Detailed health

 Challan Calculator Endpoints:
   POST /api/calculator          -- Smart challan lookup
   POST /api/admin/reload        -- Hot-reload from Supabase to RAM
   POST /api/admin/add-challan   -- Add a single challan to Supabase
   DELETE /api/admin/clear-challans -- Clear all challan data
   GET  /api/calculator/health   -- Challan health check
   GET  /api/calculator/stats    -- Memory DB stats
   GET  /api/sync-challans       -- Dump all challans for Android offline

 Legal PDF Endpoints:
   POST /api/legal-pdfs/upload   -- Upload PDF to Supabase Storage
   GET  /api/legal-pdfs/search   -- Search PDFs by name/state
   GET  /api/legal-pdfs/list     -- List all PDFs
   DELETE /api/legal-pdfs/{id}   -- Delete a PDF
=====================================================================
"""

import os
import time
import traceback
import requests as http_requests
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Supabase config
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

SUPA_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}


# =====================================================================
#  FastAPI App
# =====================================================================

app = FastAPI(
    title="Roadlaw Unified API",
    description="AI Legal Assistant + Smart Challan Calculator + Legal PDFs -- Supabase Edition",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================================
#  RAG Engine (lazy init -- heavy, loads on first request)
# =====================================================================

engine = None


def get_engine():
    global engine
    if engine is None:
        from ss2_engine import RAGEngine
        engine = RAGEngine()
    return engine


# =====================================================================
#  Challan Engine (eager -- imported at module load)
# =====================================================================

from challan_engine import (
    normalize_state,
    memory_db,
    load_from_supabase,
    add_challan_to_supabase,
    clear_all_challans,
    check_supabase_health,
    extract_offense_keywords,
    search_challans,
    CalculatorRequest,
    AddChallanRequest,
)


# =====================================================================
#  RESPONSE HELPERS
# =====================================================================

def api_success(data: dict):
    return JSONResponse(content={"success": True, "data": data})


def api_error(status: int, code: str, message: str):
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


# =====================================================================
#  REQUEST MODELS (AI Legal)
# =====================================================================

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=3)
    country: str = Field(..., min_length=2, description="e.g. India")
    state_name: str = Field(default="ALL", description="e.g. Madhya Pradesh or MP")
    city: Optional[str] = None


class IngestLocalRequest(BaseModel):
    filename: str
    country: str = "India"
    level: str = "national"
    state_name: str = "ALL"
    start_page: int = 1
    chunk_size: int = 1200


# =====================================================================
#  STARTUP -- Load challan data from Supabase into RAM
# =====================================================================

@app.on_event("startup")
async def startup():
    print("\n" + "=" * 60)
    print("  UNIFIED SERVER -- Loading challan data from Supabase")
    print("=" * 60 + "\n")

    total = await load_from_supabase()
    print(f"  [START] Challan engine ready -- {total} challans in memory")
    print(f"  [START] RAG engine will load on first /api/search request\n")


# =====================================================================
#                 AI LEGAL ENDPOINTS
# =====================================================================


# =====================================================================
#  POST /api/search -- Hierarchy-Aware RAG Search
# =====================================================================

@app.post("/api/search")
async def search(req: SearchRequest):
    start = time.time()

    try:
        eng = get_engine()
        result = eng.ask_legal_question(req.query, country=req.country, state_name=req.state_name)

        elapsed = int((time.time() - start) * 1000)

        # Build source chunks for frontend
        source_chunks = []
        citations = []
        for doc in result.get("sources", []):
            meta = doc.metadata if hasattr(doc, "metadata") else {}
            text = doc.page_content if hasattr(doc, "page_content") else str(doc)
            source_chunks.append(text)

            page = meta.get("page", 0)
            if isinstance(page, int):
                page = page + 1

            citations.append({
                "filename": meta.get("filename", "Unknown"),
                "page": page,
                "level": meta.get("level", "unknown"),
                "country": meta.get("country", "unknown"),
            })

        # Parse the answer JSON from engine
        answer_json = result.get("answer_json", {})

        return api_success({
            "answer": {
                "simplified": answer_json.get("simple_explanation", answer_json.get("primary_rule", "")),
                "legal_text": answer_json.get("primary_rule", ""),
                "raw": result.get("answer_raw", ""),
                "jurisdiction_applied": answer_json.get("jurisdiction_applied"),
                "comparison_note": answer_json.get("comparison_note"),
                "official_citations": answer_json.get("official_citations", []),
            },
            "citations": citations,
            "context_sent_to_groq": result.get("context_parts", source_chunks),
            "search_metadata": {
                "original_query": req.query,
                "expanded_query": result.get("expanded_query", req.query),
                "country_filter": req.country,
                "state_filter": req.state_name,
                "chunks_retrieved": len(source_chunks),
                "response_time_ms": elapsed,
                "engine": "LangChain + Pinecone + BM25 + Groq",
            },
        })

    except Exception as e:
        traceback.print_exc()
        return api_error(500, "SEARCH_ERROR", str(e))


# =====================================================================
#  POST /api/admin/ingest -- Upload PDF with Metadata
# =====================================================================

@app.post("/api/admin/ingest")
async def ingest_pdf(
    file: UploadFile = File(...),
    country: str = Form(default="India"),
    level: str = Form(default="national"),
    state_name: str = Form(default="ALL"),
    start_page: int = Form(default=1),
    chunk_size: int = Form(default=1200),
):
    # Validate
    if not file.filename.lower().endswith(".pdf"):
        return api_error(400, "INVALID_FILE", "Only .pdf files are allowed.")

    valid_levels = ["national", "state", "city"]
    if level.lower() not in valid_levels:
        return api_error(400, "INVALID_LEVEL", f"level must be one of: {valid_levels}")

    pdf_dir = Path("./legal_pdfs")
    pdf_dir.mkdir(exist_ok=True)
    dest = pdf_dir / file.filename

    try:
        # Save uploaded PDF
        content = await file.read()
        with open(dest, "wb") as f:
            f.write(content)

        file_size = len(content)

        # Ingest with metadata
        eng = get_engine()
        stats = eng.ingest_pdf(
            pdf_path=str(dest),
            country=country,
            level=level.lower(),
            state_name=state_name,
            start_page=max(1, start_page),
            chunk_size=max(200, chunk_size),
        )

        return api_success({
            "status": "success",
            "filename": stats["filename"],
            "file_size": f"{file_size / 1024:.1f} KB",
            "metadata": {
                "country": stats["country"],
                "level": stats["level"],
                "state_name": stats.get("state_name", "ALL"),
            },
            "pdf_info": {
                "total_pages": stats["total_pages"],
                "extracted_pages": stats["extracted_pages"],
                "skipped_pages": stats["skipped_pages"],
                "start_page": start_page,
            },
            "chunking": {
                "count": stats["total_chunks"],
            },
            "storage": {
                "pinecone_vectors": stats["total_chunks"],
                "pinecone_collection_total": stats["collection_total"],
            },
            "performance": {
                "total_time_ms": stats["time_ms"],
            },
        })

    except Exception as e:
        traceback.print_exc()
        return api_error(500, "INGEST_ERROR", str(e))


# =====================================================================
#  POST /api/admin/ingest-local -- Ingest Server-Side PDF
# =====================================================================

@app.post("/api/admin/ingest-local")
async def ingest_local(req: IngestLocalRequest):
    pdf_path = Path("./legal_pdfs") / req.filename
    if not pdf_path.exists():
        return api_error(404, "FILE_NOT_FOUND", f"{req.filename} not found in legal_pdfs/")

    try:
        eng = get_engine()
        stats = eng.ingest_pdf(
            pdf_path=str(pdf_path),
            country=req.country,
            level=req.level.lower(),
            state_name=req.state_name,
            start_page=max(1, req.start_page),
            chunk_size=max(200, req.chunk_size),
        )

        return api_success({
            "status": "success",
            "filename": stats["filename"],
            "metadata": {"country": stats["country"], "level": stats["level"]},
            "chunking": {"count": stats["total_chunks"]},
            "storage": {
                "pinecone_vectors": stats.get("total_chunks", 0),
                "pinecone_collection_total": stats.get("collection_total", 0),
            },
            "performance": {"total_time_ms": stats["time_ms"]},
        })
    except Exception as e:
        traceback.print_exc()
        return api_error(500, "INGEST_ERROR", str(e))


# =====================================================================
#  GET /api/admin/pdfs -- List Server PDFs
# =====================================================================

@app.get("/api/admin/pdfs")
async def list_pdfs():
    pdf_dir = Path("./legal_pdfs")
    pdf_dir.mkdir(exist_ok=True)

    seen = set()
    files = []
    for f in sorted(pdf_dir.iterdir()):
        if f.suffix.lower() == ".pdf" and f.name not in seen:
            seen.add(f.name)
            stat = f.stat()
            files.append({
                "filename": f.name,
                "size_bytes": stat.st_size,
                "size_display": f"{stat.st_size / 1024:.1f} KB",
            })

    return api_success({"files": files, "count": len(files)})


# =====================================================================
#  GET /api/health
# =====================================================================

@app.get("/api/health")
async def rag_health():
    return api_success({
        "server": "ok",
        "uptime": int(time.time()),
        "engine": "Unified Server -- RAG + Challan + Legal PDFs (Supabase)",
        "version": "4.0.0",
    })


# =====================================================================
#  GET /api/admin/health
# =====================================================================

@app.get("/api/admin/health")
async def admin_health():
    checks = {"server": "ok"}

    # Supabase
    supa_ok = check_supabase_health()
    checks["supabase"] = "connected" if supa_ok else "disconnected"

    # Groq
    try:
        eng = get_engine()
        eng.llm.invoke("Say OK")
        checks["groq"] = {"online": True, "models_available": 1}
    except Exception as e:
        checks["groq"] = {"online": False, "error": str(e)}

    # Pinecone
    try:
        eng = get_engine()
        stats = eng.get_stats()
        checks["pinecone"] = stats
    except Exception as e:
        checks["pinecone"] = {"error": str(e)}

    checks["lm_studio"] = {"online": False, "note": "Using HuggingFace local embeddings"}

    return api_success(checks)


# =====================================================================
#              CHALLAN CALCULATOR ENDPOINTS
# =====================================================================


# =====================================================================
#  POST /api/calculator -- Smart Challan Lookup
# =====================================================================

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


# =====================================================================
#  POST /api/admin/reload -- Hot Reload from Supabase to RAM
# =====================================================================

@app.post("/api/admin/reload")
async def reload_challans():
    try:
        print("\n  [RELOAD] Hot-reloading challan data from Supabase...\n")
        total = await load_from_supabase()
        return api_success({
            "status": "success",
            "message": "Memory DB reloaded from Supabase",
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


# =====================================================================
#  POST /api/admin/add-challan -- Add a single challan to Supabase
# =====================================================================

@app.post("/api/admin/add-challan")
async def add_challan(req: AddChallanRequest):
    """Add a single challan record to Supabase."""
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

        await add_challan_to_supabase(doc)

        # Reload memory
        await load_from_supabase()

        return api_success({
            "status": "success",
            "message": f"Added challan: {req.offense} ({req.country}/{req.state_name})",
            "record": doc,
        })
    except Exception as e:
        traceback.print_exc()
        return api_error(500, "ADD_ERROR", str(e))


# =====================================================================
#  DELETE /api/admin/clear-challans -- Clear all challan data
# =====================================================================

@app.delete("/api/admin/clear-challans")
async def clear_challans_endpoint():
    """Delete ALL challan data from Supabase and memory."""
    try:
        ok = await clear_all_challans()
        memory_db.clear()

        return api_success({
            "status": "success" if ok else "partial",
            "message": "All challan data cleared from Supabase and memory",
        })
    except Exception as e:
        traceback.print_exc()
        return api_error(500, "CLEAR_ERROR", str(e))


# =====================================================================
#  GET /api/calculator/health
# =====================================================================

@app.get("/api/calculator/health")
async def calculator_health():
    supa_ok = check_supabase_health()

    return api_success({
        "server": "ok",
        "engine": "In-Memory + Supabase + Groq LLM",
        "supabase": "connected" if supa_ok else "disconnected",
        "data_loaded": len(memory_db) > 0,
        "countries": list(memory_db.keys()),
    })


# =====================================================================
#  GET /api/sync-challans -- Dump ALL challans for Android offline
# =====================================================================

@app.get("/api/sync-challans")
async def sync_challans():
    """
    Returns a flat JSON array of every challan record for the Android app
    to download and store in its local Room Database (offline mode).
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


# =====================================================================
#  GET /api/calculator/stats -- Memory DB Stats
# =====================================================================

@app.get("/api/calculator/stats")
async def calculator_stats():
    structure = {}
    total = 0
    for country, states in memory_db.items():
        structure[country] = {}
        for state, records in states.items():
            structure[country][state] = len(records)
            total += len(records)

    return api_success({
        "total_in_memory": total,
        "total_in_supabase_json": total,
        "countries": len(memory_db),
        "structure": structure,
    })


# =====================================================================
#              LEGAL PDF ENDPOINTS (Supabase Storage)
# =====================================================================


# =====================================================================
#  POST /api/legal-pdfs/upload -- Upload PDF to Supabase Storage
# =====================================================================

@app.post("/api/legal-pdfs/upload")
async def upload_legal_pdf(
    file: UploadFile = File(...),
    display_name: str = Form(...),
    state_name: str = Form(default="ALL"),
    country: str = Form(default="India"),
    category: str = Form(default="General"),
):
    if not file.filename.lower().endswith(".pdf"):
        return api_error(400, "INVALID_FILE", "Only .pdf files are allowed.")

    try:
        content = await file.read()
        file_size = len(content)

        if file_size > 52428800:  # 50MB
            return api_error(400, "FILE_TOO_LARGE", "PDF must be under 50MB")

        # Upload to Supabase Storage
        safe_name = file.filename.replace(" ", "_")
        storage_path = f"{state_name}/{safe_name}"

        upload_url = f"{SUPABASE_URL}/storage/v1/object/legal-pdfs/{storage_path}"
        upload_resp = http_requests.post(
            upload_url,
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/pdf",
                "x-upsert": "true",
            },
            data=content,
        )

        if upload_resp.status_code not in (200, 201):
            return api_error(500, "UPLOAD_ERROR", f"Storage upload failed: {upload_resp.text[:200]}")

        # Public URL for download
        file_url = f"{SUPABASE_URL}/storage/v1/object/public/legal-pdfs/{storage_path}"

        # Save metadata to legal_pdfs table
        meta_url = f"{SUPABASE_URL}/rest/v1/legal_pdfs"
        meta_resp = http_requests.post(
            meta_url,
            headers={**SUPA_HEADERS, "Prefer": "return=representation"},
            json={
                "filename": safe_name,
                "display_name": display_name,
                "category": category,
                "country": country,
                "state_name": state_name,
                "file_size_bytes": file_size,
                "file_url": file_url,
                "storage_path": storage_path,
            },
        )

        if meta_resp.status_code not in (200, 201):
            return api_error(500, "META_ERROR", f"Metadata save failed: {meta_resp.text[:200]}")

        record = meta_resp.json()
        if isinstance(record, list) and record:
            record = record[0]

        return api_success({
            "status": "success",
            "id": record.get("id"),
            "filename": safe_name,
            "display_name": display_name,
            "state_name": state_name,
            "file_url": file_url,
            "file_size": f"{file_size / 1024:.1f} KB",
        })

    except Exception as e:
        traceback.print_exc()
        return api_error(500, "UPLOAD_ERROR", str(e))


# =====================================================================
#  GET /api/legal-pdfs/search -- Search PDFs
# =====================================================================

@app.get("/api/legal-pdfs/search")
async def search_legal_pdfs(
    q: str = Query(default="", description="Search query"),
    state_name: str = Query(default="", description="Filter by state"),
):
    try:
        url = f"{SUPABASE_URL}/rest/v1/legal_pdfs?select=*&order=created_at.desc"

        # Add filters
        if q:
            url += f"&display_name=ilike.*{q}*"
        if state_name:
            url += f"&state_name=eq.{state_name}"

        resp = http_requests.get(url, headers=SUPA_HEADERS)

        if resp.status_code != 200:
            return api_error(500, "SEARCH_ERROR", f"Supabase query failed: {resp.text[:200]}")

        results = resp.json()

        # Format results
        pdfs = []
        for r in results:
            pdfs.append({
                "id": r.get("id"),
                "filename": r.get("filename"),
                "display_name": r.get("display_name"),
                "category": r.get("category", "General"),
                "state_name": r.get("state_name", "ALL"),
                "country": r.get("country", "India"),
                "file_size": f"{r.get('file_size_bytes', 0) / 1024:.1f} KB",
                "file_size_bytes": r.get("file_size_bytes", 0),
                "file_url": r.get("file_url", ""),
                "created_at": r.get("created_at", ""),
            })

        return api_success({"pdfs": pdfs, "count": len(pdfs), "query": q})

    except Exception as e:
        traceback.print_exc()
        return api_error(500, "SEARCH_ERROR", str(e))


# =====================================================================
#  GET /api/legal-pdfs/list -- List all PDFs
# =====================================================================

@app.get("/api/legal-pdfs/list")
async def list_legal_pdfs():
    try:
        url = f"{SUPABASE_URL}/rest/v1/legal_pdfs?select=*&order=created_at.desc"
        resp = http_requests.get(url, headers=SUPA_HEADERS)

        if resp.status_code != 200:
            return api_error(500, "LIST_ERROR", f"Supabase query failed")

        results = resp.json()
        pdfs = []
        for r in results:
            pdfs.append({
                "id": r.get("id"),
                "filename": r.get("filename"),
                "display_name": r.get("display_name"),
                "category": r.get("category", "General"),
                "state_name": r.get("state_name", "ALL"),
                "file_size": f"{r.get('file_size_bytes', 0) / 1024:.1f} KB",
                "file_size_bytes": r.get("file_size_bytes", 0),
                "file_url": r.get("file_url", ""),
                "created_at": r.get("created_at", ""),
            })

        return api_success({"pdfs": pdfs, "count": len(pdfs)})

    except Exception as e:
        traceback.print_exc()
        return api_error(500, "LIST_ERROR", str(e))


# =====================================================================
#  DELETE /api/legal-pdfs/{pdf_id} -- Delete a PDF
# =====================================================================

@app.delete("/api/legal-pdfs/{pdf_id}")
async def delete_legal_pdf(pdf_id: int):
    try:
        # Get metadata first for storage path
        get_url = f"{SUPABASE_URL}/rest/v1/legal_pdfs?id=eq.{pdf_id}&select=storage_path"
        get_resp = http_requests.get(get_url, headers=SUPA_HEADERS)

        if get_resp.status_code == 200 and get_resp.json():
            storage_path = get_resp.json()[0].get("storage_path", "")

            # Delete from storage
            if storage_path:
                del_storage_url = f"{SUPABASE_URL}/storage/v1/object/legal-pdfs/{storage_path}"
                http_requests.delete(del_storage_url, headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                })

        # Delete metadata
        del_url = f"{SUPABASE_URL}/rest/v1/legal_pdfs?id=eq.{pdf_id}"
        del_resp = http_requests.delete(del_url, headers=SUPA_HEADERS)

        return api_success({"status": "deleted", "id": pdf_id})

    except Exception as e:
        traceback.print_exc()
        return api_error(500, "DELETE_ERROR", str(e))


# =====================================================================
#  RUN
# =====================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Roadlaw Unified Server v4.0 -- port 3000")
    print("  AI Legal + Challan + Legal PDFs (Supabase)")
    print("=" * 60 + "\n")

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=3000,
        reload=False,
        log_level="info",
    )
