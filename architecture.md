# 🏗️ Roadlaw — Complete Project Architecture

## 1. High-Level System Overview

```mermaid
graph TB
    subgraph USER["👤 User's Phone"]
        APP["📱 Roadlaw Android App"]
    end

    subgraph CLOUD["☁️ Cloud Services"]
        RENDER["🖥️ Render Server<br/>(FastAPI Backend)"]
        SUPA["🗄️ Supabase<br/>(PostgreSQL + JSON Storage)"]
        PINE["🌲 Pinecone<br/>(Vector Database)"]
        GROQ["🤖 Groq AI<br/>(LLaMA 4 Scout LLM)"]
        HF["🤗 HuggingFace API<br/>(Embeddings)"]
    end

    APP -->|"API Calls (HTTPS)"| RENDER
    APP -->|"Download PDFs/JSON"| SUPA
    RENDER -->|"RAG Search"| PINE
    RENDER -->|"Text to Vector"| HF
    RENDER -->|"AI Answers"| GROQ
    RENDER -->|"PDF Metadata & Data"| SUPA
```

---

## 2. Android App Architecture

```mermaid
graph LR
    subgraph ANDROID["📱 Android App"]
        MA["MainActivity.java"]
        WV["WebView"]
        BRIDGE["AndroidBridge<br/>(JS Interface)"]
        DM["DownloadManager"]
        GEO["Geocoder<br/>(GPS → State)"]
    end

    subgraph WEBUI["🌐 index.html (Single Page App)"]
        HOME["🏠 Home Page"]
        AI["🤖 AI Legal Assistant"]
        CALC["💰 Challan Calculator"]
        LEGAL["📄 Legal PDFs"]
        PROFILE["👤 Profile"]
        ADMIN["🔧 Admin Panel"]
    end

    MA --> WV
    WV --> WEBUI
    BRIDGE -->|"downloadFile()"| DM
    BRIDGE -->|"getStateName()"| GEO
    BRIDGE -->|"searchChallanOffline()"| MA
    WV -->|"window.AndroidBridge"| BRIDGE
```

### App Pages (Single Page Application)

| Page | Description | Key Features |
|------|-------------|-------------|
| 🏠 **Home** | Landing page with quick actions | Quick chips, GPS location display |
| 🤖 **AI Assistant** | Chat with AI | RAG-powered, state-specific answers |
| 💰 **Challan Calculator** | Fine estimation tool | Online + Offline mode, keyword matching |
| 📄 **Legal PDFs** | State law documents | Browse, search, download PDFs |
| 👤 **Profile** | User settings & downloads | Downloaded PDFs list, dark mode |
| 🔧 **Admin** | Document & data management | Upload PDFs to Pinecone, manage JSON |

### Key Files

| File | Path | Purpose |
|------|------|---------|
| `MainActivity.java` | `app/src/main/java/.../` | Android WebView + JS Bridge |
| `index.html` | `app/src/main/assets/` | Full SPA UI (~2480 lines) |
| `AndroidManifest.xml`| `app/src/main/` | Permissions & app config |

---

## 3. Backend Architecture

```mermaid
graph TB
    subgraph SERVER["🖥️ FastAPI Server (server.py)"]
        direction TB
        API["API Router<br/>/api/*"]
        
        subgraph ENGINES["⚙️ Engines"]
            RAG["ss2_engine.py<br/>RAG Search Engine"]
            CH["challan_engine.py<br/>Challan Calculator"]
        end
    end

    API -->|"/api/search"| RAG
    API -->|"/api/calculator"| CH
    API -->|"/api/legal-pdfs/*"| SUPA_CLIENT["Supabase Client"]
    
    RAG -->|"Embed Query"| HF["🤗 HuggingFace API<br/>all-mpnet-base-v2"]
    RAG -->|"Vector Search"| PINE["🌲 Pinecone"]
    RAG -->|"Generate Answer"| GROQ["🤖 Groq LLM<br/>LLaMA 4 Scout"]
    
    CH -->|"Load JSON"| SUPA_STORAGE["🗄️ Supabase Storage<br/>(challans.json)"]
    CH -->|"AI Analysis"| GROQ
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Server health check |
| `POST` | `/api/search` | AI-powered legal search (RAG) |
| `POST` | `/api/calculator` | Challan fine calculator |
| `GET` | `/api/legal-pdfs/search?q=` | Search legal PDFs in Supabase |
| `GET` | `/api/legal-pdfs/list` | List all legal PDFs |
| `POST` | `/api/legal-pdfs/upload` | Upload PDF to Supabase Storage |
| `GET` | `/api/sync-challans` | Download challans.json |
| `POST` | `/api/admin/ingest` | Process PDF & upload vectors to Pinecone |

### Backend Files

| File | Purpose |
|------|---------|
| `server.py` | Main FastAPI server — API endpoints |
| `ss2_engine.py` | RAG engine — HF API embeddings, Pinecone, Groq LLM |
| `challan_engine.py` | Challan engine — Supabase JSON parsing, fine logic |
| `requirements.txt` | Python dependencies (API-only, no heavy torch) |
| `.env` | Environment variables (Pinecone, Groq, Supabase, HF) |

---

## 4. Data Flow Diagrams

### 4.1 AI Legal Search Flow

```mermaid
sequenceDiagram
    actor User
    participant App as 📱 App (index.html)
    participant Backend as 🖥️ FastAPI
    participant HF as 🤗 HF API
    participant Pinecone as 🌲 Pinecone
    participant Groq as 🤖 Groq LLM

    User->>App: "Helmet rule in my state"
    Note over App: Detect state from GPS<br/>e.g. "Madhya Pradesh"
    App->>Backend: POST /api/search
    Backend->>HF: Get Embeddings for query
    HF-->>Backend: 768-dim vector
    Backend->>Pinecone: Vector similarity search<br/>(filter: state = MP or National)
    Pinecone-->>Backend: Top matching chunks
    Backend->>Groq: System prompt + Chunks + Query
    Groq-->>Backend: LLaMA 4 Generated answer
    Backend-->>App: {answer, sources[]}
    App-->>User: Display formatted answer
```

### 4.2 Challan Calculator Flow (Online & Offline)

```mermaid
sequenceDiagram
    actor User
    participant App as 📱 App
    participant Bridge as 🔗 AndroidBridge
    participant Backend as 🖥️ FastAPI
    participant Supa as 🗄️ Supabase Storage

    User->>App: Open App (First Time)
    App->>Supa: Download challans.json
    Supa-->>App: Save to local device storage
    
    User->>App: Search "Red light jump" (Offline)
    App->>Bridge: searchChallanOffline()
    Bridge->>Bridge: Keyword fuzzy matching on local JSON
    Bridge-->>App: Return matching fines
    App-->>User: Show fine instantly

    Note over App: If Online Mode Used:
    App->>Backend: POST /api/calculator
    Backend->>Supa: Fetch/Read challans.json
    Backend-->>App: AI analyzed fine details
```

### 4.3 PDF Download Flow

```mermaid
sequenceDiagram
    actor User
    participant App as 📱 App
    participant Bridge as 🔗 AndroidBridge
    participant DM as 📥 DownloadManager
    participant Supabase as 🗄️ Supabase Storage

    User->>App: Tap "Download PDF"
    App->>Bridge: downloadFile(url)
    Bridge->>DM: Enqueue Android download
    DM->>Supabase: HTTPS GET PDF file
    Supabase-->>DM: File stream
    DM-->>User: 📱 System Notification
    App->>App: Save to localStorage (Profile)
```

---

## 5. Database Schema & Storage

### 5.1 Supabase SQL (Metadata)
```sql
CREATE TABLE legal_pdfs (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    display_name TEXT,
    category TEXT DEFAULT 'State Law',
    state_name TEXT DEFAULT 'ALL',
    country TEXT DEFAULT 'India',
    file_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.2 Supabase Storage Buckets
| Bucket Name | Content | Access |
|-------------|---------|--------|
| `legal-pdfs` | Motor Vehicle Rules PDF files | Public |
| `app-data` | `challans.json` for offline syncing | Public |

### 5.3 Pinecone (Vector DB)
- **Index:** `roadlaw-legal`
- **Dimension:** 768 (`all-mpnet-base-v2`)
- **Metric:** Cosine Similarity
- **Metadata stored per vector:** `country`, `state_name`, `source_pdf`, `page_num`

---

## 6. Deployment Architecture

```mermaid
graph TB
    subgraph GITHUB["📦 GitHub"]
        REPO1["Roadlawfull<br/>(Full App + API)"]
        REPO2["Roadlaw<br/>(Backend API Only)"]
    end

    subgraph RENDER["🚀 Render Cloud"]
        WEB["FastAPI Web Service<br/>(roadlaw.onrender.com)"]
    end

    subgraph SERVICES["☁️ Cloud APIs (Free Tier)"]
        S1["Supabase (SQL + Storage)"]
        S2["Pinecone (Vector DB)"]
        S3["Groq (LLaMA 4 API)"]
        S4["HuggingFace (Embeddings API)"]
    end

    REPO2 -->|"Auto Deploy"| WEB
    WEB --> S1
    WEB --> S2
    WEB --> S3
    WEB --> S4
```

### Environment Variables (.env)
| Key | Purpose |
|-----|---------|
| `GROQ_API_KEY` | For LLaMA 4 Scout LLM text generation |
| `PINECONE_API_KEY` | For RAG vector similarity search |
| `SUPABASE_URL` | For database and storage connection |
| `SUPABASE_SERVICE_KEY` | For admin access to Supabase |
| `HF_API_KEY` | For HuggingFace Embeddings (saves Render RAM) |

---

## 7. Tech Stack Overview

- **Frontend:** HTML, CSS, JS, TailwindCSS within Android WebView
- **Mobile Native:** Java, Android SDK (DownloadManager, Geocoder)
- **Backend Framework:** Python 3.11, FastAPI, Uvicorn
- **AI/RAG:** LangChain, HuggingFace API (`all-mpnet-base-v2`)
- **LLM Model:** Groq API (`meta-llama/llama-4-scout-17b-16e-instruct`)
- **Databases:** Supabase (PostgreSQL), Pinecone (Vectors)
- **Hosting:** Render (Cloud Platform)
