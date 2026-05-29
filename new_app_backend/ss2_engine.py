"""
═══════════════════════════════════════════════════════════
 RAG Engine v2 — ss2_engine.py  (Pinecone Cloud Edition)
═══════════════════════════════════════════════════════════
 Global-scale RAG with:
   - Pinecone cloud vector DB (replaces local ChromaDB)
   - Country/Level/State metadata on every chunk
   - Hierarchy-aware retrieval (City > State > National)
   - Query rewriting for weak retrieval
   - Hybrid search (Vector + BM25)

 Metadata per chunk:
   { country: "India", level: "national"|"state"|"city",
     state_name: "ALL"|"Madhya Pradesh"|...,
     filename: "...", page: N, chunk_index: N }
═══════════════════════════════════════════════════════════
"""

import os
import time
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY not found in .env file")

# ── LangChain imports ──
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.retrievers import BM25Retriever
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

# ── Pinecone imports ──
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore


# ═══════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════

PDF_FOLDER = "./legal_pdfs"
EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
PINECONE_INDEX_NAME = "roadlaw-legal"
PINECONE_CLOUD = "aws"
PINECONE_REGION = "us-east-1"
EMBEDDING_DIMENSION = 768  # all-mpnet-base-v2 outputs 768-dim vectors
LLM_MODEL = "llama-3.3-70b-versatile"
TOP_K = 5
RETRIEVAL_THRESHOLD = 1.2

# ═══════════════════════════════════════════════════════════
#  STATE ALIASES — imported from challan_engine (single source of truth)
# ═══════════════════════════════════════════════════════════

from challan_engine import STATE_ALIASES, normalize_state



# ═══════════════════════════════════════════════════════════
#  PROMPTS
# ═══════════════════════════════════════════════════════════

RAG_PROMPT = """You are an expert Indian Legal Advisor with deep knowledge of traffic and motor vehicle laws.

STRICT RULES:
1. Use ONLY the provided context. NEVER hallucinate or invent laws.
2. If the answer is not in the context, say "This information was not found in the available legal database."
3. Each document in the context has a [Jurisdiction Level] tag: national, state, or city.

CONFLICT RESOLUTION (CRITICAL):
- If you find conflicting rules across different jurisdiction levels, ALWAYS prioritize the MOST SPECIFIC local rule.
- Priority order: City > State > National
- The City-level rule overrides State, and State overrides National.
- Still mention the higher-level rules as comparison.

You MUST respond in this EXACT JSON format (no markdown, no extra text):
{{
  "primary_rule": "The most specific applicable law text with fine amounts",
  "jurisdiction_applied": "city / state / national",
  "comparison_note": "Differences with other jurisdiction levels, or null if no conflict",
  "official_citations": ["Section/Rule number — jurisdiction level"],
  "simple_explanation": "Plain language explanation a non-lawyer can understand"
}}

Context:
{context}

Question:
{question}

Answer (JSON only):"""

REWRITE_PROMPT = """Rewrite the following user query into legal terminology and keyword-heavy phrasing optimized for retrieval from Indian traffic law documents.

Do NOT answer the query. Output ONLY the rewritten search query. No headers, labels, or explanations.

User Query:
{query}"""


# ═══════════════════════════════════════════════════════════
#  RAG ENGINE CLASS (Pinecone)
# ═══════════════════════════════════════════════════════════

class RAGEngine:

    def __init__(self):
        print("\n" + "=" * 60)
        print("  ROADLAW RAG ENGINE v2 — Pinecone Cloud Edition")
        print("=" * 60)

        # ── Embedding model ──
        print("\n  Loading embedding model...")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        # ── Pinecone vector store ──
        self.vectorstore = None
        self.bm25_retriever = None
        self._init_vectorstore()

        # ── Groq LLM ──
        print("\n  Loading Groq LLM...")
        self.llm = ChatGroq(
            groq_api_key=GROQ_API_KEY,
            model_name=LLM_MODEL,
            temperature=0,
        )

        self.rag_prompt = PromptTemplate(
            template=RAG_PROMPT,
            input_variables=["context", "question"],
        )

        print("\n  RAG Engine ready!\n")

    # ─────────────────────────────────────────────────────
    #  VECTOR STORE INIT (Pinecone)
    # ─────────────────────────────────────────────────────

    def _init_vectorstore(self):
        print("\n  Connecting to Pinecone cloud...")
        pc = Pinecone(api_key=PINECONE_API_KEY)

        # Create index if it doesn't exist
        existing_indexes = [idx.name for idx in pc.list_indexes()]
        if PINECONE_INDEX_NAME not in existing_indexes:
            print(f"  Creating new Pinecone index '{PINECONE_INDEX_NAME}'...")
            pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=EMBEDDING_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
            )
            # Wait for index to be ready
            import time as _t
            while not pc.describe_index(PINECONE_INDEX_NAME).status.get("ready", False):
                print("  Waiting for index to be ready...")
                _t.sleep(2)
            print(f"  Index '{PINECONE_INDEX_NAME}' created!")
        else:
            print(f"  Found existing index '{PINECONE_INDEX_NAME}'")

        index = pc.Index(PINECONE_INDEX_NAME)

        # Get stats
        stats = index.describe_index_stats()
        total_vectors = stats.get("total_vector_count", 0)
        print(f"  Pinecone index has {total_vectors} vectors")

        # Create LangChain PineconeVectorStore
        self.vectorstore = PineconeVectorStore(
            index=index,
            embedding=self.embeddings,
            text_key="text",
        )

        # Init BM25 from Pinecone data (fetch all docs for BM25)
        if total_vectors > 0:
            print(f"  Loading docs for BM25 retriever...")
            try:
                # Fetch a sample for BM25 — Pinecone doesn't support get_all easily
                # Use a dummy query to fetch TOP docs for BM25 init
                sample_docs = self.vectorstore.similarity_search("law rule fine penalty", k=min(total_vectors, 500))
                if sample_docs:
                    print(f"  Initializing BM25 retriever ({len(sample_docs)} chunks)...")
                    self.bm25_retriever = BM25Retriever.from_documents(sample_docs)
                    self.bm25_retriever.k = TOP_K
            except Exception as e:
                print(f"  BM25 init skipped: {e}")
                self.bm25_retriever = None
        else:
            self.bm25_retriever = None

    # ─────────────────────────────────────────────────────
    #  INGEST PDF WITH METADATA
    # ─────────────────────────────────────────────────────

    def ingest_pdf(self, pdf_path, country="India", level="national", state_name="ALL", start_page=1, chunk_size=1200):
        """
        Ingest a single PDF with country/level metadata.
        Every chunk gets: { country, level, state_name, filename, page, chunk_index }
        """
        start = time.time()
        filename = os.path.basename(pdf_path)

        print(f"\n  Ingesting: {filename}")
        print(f"  Country: {country} | Level: {level} | State: {state_name} | Start page: {start_page}")

        # Load PDF
        loader = PyPDFLoader(str(pdf_path))
        all_pages = loader.load()
        print(f"  Total pages: {len(all_pages)}")

        # Filter pages (skip before start_page)
        pages = [p for p in all_pages if (p.metadata.get("page", 0) + 1) >= start_page]
        print(f"  Pages after skip (start_page={start_page}): {len(pages)}")

        if not pages:
            raise ValueError(f"No pages found after start_page={start_page}")

        # Strip Hindi if configured
        strip_hindi = os.getenv("STRIP_HINDI", "false").lower() == "true"
        if strip_hindi:
            import re
            print("  Stripping Hindi characters (Devanagari script)...")
            for page in pages:
                page.page_content = re.sub(r'[\u0900-\u097F]+', '', page.page_content)
                page.page_content = re.sub(r' +', ' ', page.page_content)

        # Inject base metadata into every page
        resolved_state = normalize_state(state_name)
        for page in pages:
            page.metadata["filename"] = filename
            page.metadata["country"] = country
            page.metadata["level"] = level
            page.metadata["state_name"] = resolved_state
            # Pinecone requires metadata values to be str/int/float/bool/list
            # Remove 'source' if it's a file path (too long/complex)
            if "source" in page.metadata:
                page.metadata["source"] = os.path.basename(str(page.metadata["source"]))

        # Split into chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=250,
            separators=["\n\n", "\n", ".", " ", ""],
        )
        chunks = splitter.split_documents(pages)
        print(f"  Chunks created: {len(chunks)}")

        # Add chunk_index to metadata
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["total_chunks"] = len(chunks)

        # Add to Pinecone
        if chunks:
            # Pinecone add_documents in batches of 100
            batch_size = 100
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i+batch_size]
                self.vectorstore.add_documents(batch)
                print(f"  Uploaded batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")

        # Rebuild BM25 with new chunks added
        if chunks:
            try:
                all_bm25_docs = chunks  # Use current chunks for BM25 refresh
                if self.bm25_retriever:
                    # Merge with existing
                    existing = self.bm25_retriever.docs if hasattr(self.bm25_retriever, 'docs') else []
                    all_bm25_docs = list(existing) + chunks
                self.bm25_retriever = BM25Retriever.from_documents(all_bm25_docs)
                self.bm25_retriever.k = TOP_K
            except Exception as e:
                print(f"  BM25 rebuild note: {e}")

        # Get updated stats
        pc = Pinecone(api_key=PINECONE_API_KEY)
        idx = pc.Index(PINECONE_INDEX_NAME)
        stats = idx.describe_index_stats()
        collection_total = stats.get("total_vector_count", 0)

        elapsed = int((time.time() - start) * 1000)
        print(f"  Done in {elapsed}ms | Total vectors in Pinecone: {collection_total}\n")

        return {
            "filename": filename,
            "country": country,
            "level": level,
            "state_name": resolved_state,
            "total_pages": len(all_pages),
            "extracted_pages": len(pages),
            "skipped_pages": start_page - 1,
            "total_chunks": len(chunks),
            "collection_total": collection_total,
            "time_ms": elapsed,
        }

    # ─────────────────────────────────────────────────────
    #  CLEAR ALL DATA
    # ─────────────────────────────────────────────────────

    def clear_all(self):
        """Delete the Pinecone index and recreate it."""
        print("  Clearing Pinecone index...")
        pc = Pinecone(api_key=PINECONE_API_KEY)
        try:
            pc.delete_index(PINECONE_INDEX_NAME)
            print(f"  Deleted index '{PINECONE_INDEX_NAME}'")
        except Exception as e:
            print(f"  Delete note: {e}")
        # Recreate
        self._init_vectorstore()

    # ─────────────────────────────────────────────────────
    #  REINGEST ALL PDFs
    # ─────────────────────────────────────────────────────

    def reingest_all(self, country="India", level="national"):
        start = time.time()

        # Clear Pinecone
        self.clear_all()

        # Ingest all PDFs
        pdf_dir = Path(PDF_FOLDER)
        total_chunks = 0
        total_pages = 0

        for f in sorted(pdf_dir.glob("*.[pP][dD][fF]")):
            stats = self.ingest_pdf(str(f), country=country, level=level)
            total_chunks += stats["total_chunks"]
            total_pages += stats["total_pages"]

        elapsed = int((time.time() - start) * 1000)
        return {
            "total_pages": total_pages,
            "total_chunks": total_chunks,
            "time_ms": elapsed,
        }

    # ─────────────────────────────────────────────────────
    #  QUERY REWRITING
    # ─────────────────────────────────────────────────────

    def rewrite_query(self, query):
        print("  Weak retrieval — rewriting query...")
        rewritten = self.llm.invoke(REWRITE_PROMPT.format(query=query))
        return rewritten.content.strip()

    # ─────────────────────────────────────────────────────
    #  HYBRID RETRIEVAL WITH COUNTRY/STATE FILTER
    # ─────────────────────────────────────────────────────

    def hybrid_retrieve(self, query, country=None, state_name="ALL"):
        """
        Hybrid search: Pinecone Vector (with metadata filter) + BM25.
        Pinecone supports metadata filtering natively.
        """

        # ── Vector search with metadata filter ──
        search_kwargs = {"k": 8}

        if country:
            resolved = normalize_state(state_name)
            if resolved and resolved != "ALL":
                # Pinecone filter: country matches AND (state_name is ALL OR matches)
                search_kwargs["filter"] = {
                    "$and": [
                        {"country": {"$eq": country}},
                        {
                            "$or": [
                                {"state_name": {"$eq": "ALL"}},
                                {"state_name": {"$eq": resolved}},
                            ]
                        },
                    ]
                }
            else:
                search_kwargs["filter"] = {"country": {"$eq": country}}

        vector_results = self.vectorstore.similarity_search_with_score(
            query, **search_kwargs
        )

        vector_docs = []
        best_score = None

        if vector_results:
            # Pinecone returns (doc, score) where score is cosine similarity (higher=better)
            # Convert to distance-like score for threshold comparison (lower=better)
            best_score = 1.0 - vector_results[0][1]  # cosine distance = 1 - similarity
            vector_docs = [doc for doc, score in vector_results]

            # Log scores
            for doc, score in vector_results:
                level = doc.metadata.get("level", "?")
                state = doc.metadata.get("state_name", "?")
                print(f"    [{level}/{state}] sim={score:.4f} — {doc.page_content[:80]}...")

        # ── BM25 search ──
        bm25_docs = []
        if self.bm25_retriever:
            bm25_docs = self.bm25_retriever.invoke(query)
            # Filter BM25 results by country too
            if country:
                bm25_docs = [d for d in bm25_docs if d.metadata.get("country") == country]

        # ── Merge + deduplicate ──
        combined = []
        seen = set()
        for doc in vector_docs + bm25_docs:
            meta = doc.metadata or {}
            key = (
                meta.get("source", meta.get("filename", ""))
                + str(meta.get("page", ""))
                + doc.page_content[:100]
            )
            if key not in seen:
                seen.add(key)
                combined.append(doc)

        return combined, best_score

    # ─────────────────────────────────────────────────────
    #  MAIN SEARCH — Hierarchy-Aware
    # ─────────────────────────────────────────────────────

    def ask_legal_question(self, query, country="India", state_name="ALL"):
        """
        Full RAG pipeline with hierarchy awareness:
        1. Hybrid retrieve (filtered by country + state)
        2. If weak → rewrite → re-retrieve
        3. Format context with [Jurisdiction Level] tags
        4. LLM generates hierarchy-aware JSON answer
        """
        print(f"\n{'='*60}")
        print(f"  SEARCH: \"{query}\" | country={country} | state={state_name}")
        print(f"{'='*60}")

        # ── Step 1: Initial retrieval ──
        docs, score = self.hybrid_retrieve(query, country=country, state_name=state_name)
        expanded_query = query

        # ── Step 2: Fallback rewrite if weak ──
        if score is None or score > RETRIEVAL_THRESHOLD:
            rewritten = self.rewrite_query(query)
            expanded_query = rewritten
            print(f"  Rewritten: {rewritten}")
            docs, score = self.hybrid_retrieve(rewritten, country=country, state_name=state_name)

        # ── No results ──
        if not docs:
            return {
                "answer_json": {
                    "primary_rule": "No relevant legal information found in the database.",
                    "jurisdiction_applied": None,
                    "comparison_note": None,
                    "official_citations": [],
                    "simple_explanation": "No matching laws were found. Please try a different query.",
                },
                "answer_raw": "No relevant legal information found.",
                "sources": [],
                "expanded_query": expanded_query,
            }

        # ── Step 3: Format context with hierarchy tags ──
        level_order = {"city": 0, "state": 1, "national": 2}
        docs.sort(key=lambda d: level_order.get(d.metadata.get("level", "national"), 2))

        context_parts = []
        for doc in docs:
            level = doc.metadata.get("level", "unknown").upper()
            filename = doc.metadata.get("filename", "Unknown")
            page = doc.metadata.get("page", "?")
            if isinstance(page, int):
                page = page + 1

            header = f"[Jurisdiction Level: {level}] [Source: {filename}, Page {page}]"
            context_parts.append(f"{header}\n{doc.page_content}")

        context_text = "\n\n---\n\n".join(context_parts)

        # ── Step 4: Generate answer via Groq ──
        print(f"  Generating answer ({len(docs)} chunks, {len(context_text)} chars)...")

        final_prompt = self.rag_prompt.format(
            context=context_text,
            question=query,
        )

        response = self.llm.invoke(final_prompt)
        raw_answer = response.content.strip()

        # Try to parse JSON
        answer_json = None
        try:
            import json
            clean = raw_answer
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            answer_json = json.loads(clean)
        except Exception:
            answer_json = {
                "primary_rule": raw_answer,
                "jurisdiction_applied": None,
                "comparison_note": None,
                "official_citations": [],
                "simple_explanation": raw_answer,
            }

        print(f"  Search complete\n{'='*60}\n")

        return {
            "answer_json": answer_json,
            "answer_raw": raw_answer,
            "sources": docs,
            "context_parts": context_parts,
            "expanded_query": expanded_query,
        }

    # ─────────────────────────────────────────────────────
    #  STATS
    # ─────────────────────────────────────────────────────

    def get_stats(self):
        try:
            pc = Pinecone(api_key=PINECONE_API_KEY)
            idx = pc.Index(PINECONE_INDEX_NAME)
            stats = idx.describe_index_stats()
            count = stats.get("total_vector_count", 0)
        except Exception:
            count = 0
        return {"document_count": count, "backend": "pinecone"}
