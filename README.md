# 🚗 Roadlaw — AI-Powered Traffic Law Assistant for India

<p align="center">
  <b>An Android app that helps Indian drivers understand traffic laws, calculate challans, and access state-specific legal documents — powered by AI.</b>
</p>

---

## 📥 Quick Install (APK Download)

> **No setup needed!** Download the APK directly and install on your Android phone.

| File | Size | Description |
|------|------|-------------|
| [`Roadlaw-debug.apk`](./Roadlaw-debug.apk) | ~11 MB | Ready-to-install debug APK |

### How to install:
1. Download `Roadlaw-debug.apk` from this repo
2. Transfer to your Android phone (or download directly on phone)
3. Open the APK file → Tap "Install" (allow unknown sources if prompted)
4. Open the app → Allow Location & Notification permissions when asked
5. Start using! 🎉

> ⚠️ **Note:** The debug APK comes with `YOUR_GROQ_API_KEY_HERE` placeholder. To use the AI Assistant feature, you need to build the app yourself with your own Groq API key (see [Setup Guide](#-setup-guide) below).

---

## ✨ Features

| Feature | Description | Online/Offline |
|---------|-------------|---------------|
| 🤖 **AI Legal Assistant** | Ask traffic law questions in English/Hindi. Gets state-specific answers using RAG | Online |
| 💰 **Challan Calculator** | Enter violation → Get exact fine amount with AI analysis | Both ✅ |
| 📄 **Legal PDFs** | Browse & download state-wise Motor Vehicle Rules | Online (download for offline) |
| 📍 **GPS Auto-Detect** | Automatically detects your state and shows relevant laws | Online |
| 📶 **Offline Mode** | Challan calculator works without internet using cached data | Offline ✅ |
| 👤 **Profile** | View downloaded PDFs, dark mode toggle, server settings | Offline ✅ |

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    📱 Android App                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │           WebView (index.html)                    │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌───────┐  │   │
│  │  │ Home │ │  AI  │ │Calc  │ │ PDFs │ │Profile│  │   │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └───────┘  │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │ AndroidBridge (JS↔Java)        │
│  ┌──────────────────────┴───────────────────────────┐   │
│  │           MainActivity.java                       │   │
│  │  GPS Location │ DownloadManager │ Offline Search  │   │
│  └───────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTPS API Calls
                          ▼
┌─────────────────────────────────────────────────────────┐
│              🖥️ Backend (Render Cloud)                   │
│              https://roadlaw.onrender.com                │
│  ┌──────────────────────────────────────────────────┐   │
│  │              FastAPI Server (server.py)            │   │
│  │  ┌──────────────┐    ┌──────────────────┐        │   │
│  │  │ ss2_engine.py│    │challan_engine.py │        │   │
│  │  │  RAG Search  │    │ Fine Calculator  │        │   │
│  │  └──────┬───────┘    └────────┬─────────┘        │   │
│  └─────────┼─────────────────────┼──────────────────┘   │
└────────────┼─────────────────────┼──────────────────────┘
             │                     │
    ┌────────┼────────┐   ┌────────┼────────┐
    ▼        ▼        ▼   ▼                 ▼
┌──────┐ ┌──────┐ ┌──────┐           ┌──────────┐
│Pine- │ │ Groq │ │Supa- │           │ Supabase │
│cone  │ │  AI  │ │base  │           │ Storage  │
│Vector│ │(LLM) │ │(SQL) │           │(JSON+PDF)│
│  DB  │ │      │ │      │           │          │
└──────┘ └──────┘ └──────┘           └──────────┘
```

---

## 📁 Project Structure

```
ROADSAFTEY/
│
├── 📄 README.md                          ← You are here
├── 📦 Roadlaw-debug.apk                  ← Install directly on phone
├── 📄 .gitignore
├── 📄 build.gradle.kts                   ← Root Gradle config
├── 📄 settings.gradle.kts                ← Project settings
├── 📄 gradle.properties                  ← Gradle properties
├── 📄 gradlew / gradlew.bat             ← Gradle wrapper scripts
│
├── 📁 app/                               ← 📱 ANDROID APP
│   ├── 📄 build.gradle.kts              ← App-level Gradle config
│   └── 📁 src/main/
│       ├── 📄 AndroidManifest.xml        ← Permissions & app config
│       │
│       ├── 📁 assets/                    ← Web UI files (loaded in WebView)
│       │   ├── 📄 index.html             ← ⭐ MAIN APP UI (2480 lines)
│       │   ├── 📁 css/                   ← TailwindCSS, Material Symbols
│       │   ├── 📁 fonts/                 ← Plus Jakarta Sans font files
│       │   └── 📁 js/                    ← Supabase JS client
│       │
│       ├── 📁 java/com/bgi/roadlaw/
│       │   └── 📄 MainActivity.java      ← ⭐ ANDROID NATIVE CODE (375 lines)
│       │
│       └── 📁 res/                       ← Icons, layouts, themes, colors
│
├── 📁 new_app_backend/                   ← 🖥️ BACKEND SERVER
│   ├── 📄 server.py                      ← ⭐ FastAPI server (all endpoints)
│   ├── 📄 ss2_engine.py                  ← ⭐ RAG search engine
│   ├── 📄 challan_engine.py              ← ⭐ Challan calculator engine
│   ├── 📄 requirements.txt              ← Python dependencies
│   ├── 📄 .env.example                   ← Environment variable template
│   ├── 📄 .python-version               ← Python 3.11.9
│   ├── 📄 challans_dump.json            ← Offline challan data
│   ├── 📄 batch_ingest.py               ← Bulk PDF ingestion script
│   ├── 📄 upload_to_supabase.py         ← Upload PDFs to Supabase
│   ├── 📄 register_pdfs_in_db.py        ← Register PDFs in database
│   └── 📄 supabase_setup.sql            ← Database schema SQL
│
├── 📁 challan/                           ← Old challan scripts (legacy)
│   ├── 📄 import_docx.py
│   └── 📄 requirements.txt
│
└── 📁 gradle/                            ← Gradle wrapper files
    ├── 📄 libs.versions.toml
    └── 📁 wrapper/
```

---

## 🛠️ Setup Guide

### Prerequisites

| Tool | Version | Download Link |
|------|---------|---------------|
| Android Studio | Latest (Ladybug+) | [developer.android.com](https://developer.android.com/studio) |
| Java JDK | 11+ | Comes with Android Studio |
| Python | 3.11.x | [python.org](https://www.python.org/downloads/) |
| Git | Latest | [git-scm.com](https://git-scm.com/) |

### Free Accounts Needed

| Service | Purpose | Sign Up |
|---------|---------|---------|
| **Groq** | AI/LLM for answers | [console.groq.com](https://console.groq.com/) |
| **Pinecone** | Vector database for RAG search | [pinecone.io](https://www.pinecone.io/) |
| **Supabase** | PostgreSQL + PDF file storage | [supabase.com](https://supabase.com/) |
| **Render** | Cloud hosting for backend | [render.com](https://render.com/) |

> 💡 All services have **free tiers** that are sufficient for this project.

---

### Step 1: Clone the Repository

```bash
git clone https://github.com/deependrasinghsolanki03-alt/Roadlawfull.git
cd Roadlawfull
```

---

### Step 2: Setup Backend

#### 2.1 Create `.env` file

```bash
cd new_app_backend
```

Create a file called `.env` (no extension) with the following content:

```env
# ============================================
#  ROADLAW BACKEND — ENVIRONMENT VARIABLES
# ============================================

# 🤖 Groq AI (for LLM answers)
# Get from: https://console.groq.com/keys
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 🌲 Pinecone (Vector Database for RAG search)
# Get from: https://app.pinecone.io → API Keys
PINECONE_API_KEY=pcsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 🗄️ Supabase (PostgreSQL + Storage)
# Get from: https://supabase.com → Project Settings → API
SUPABASE_URL=https://xxxxxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxxxx
```

#### 2.2 What each variable does

| Variable | Service | Where to Find | Used For |
|----------|---------|---------------|----------|
| `GROQ_API_KEY` | Groq | Console → API Keys | AI answers for legal queries & challan analysis |
| `PINECONE_API_KEY` | Pinecone | Dashboard → API Keys | Storing & searching legal document vectors |
| `SUPABASE_URL` | Supabase | Settings → API → Project URL | Database & PDF file storage |
| `SUPABASE_SERVICE_KEY` | Supabase | Settings → API → `service_role` key | Admin access to storage buckets |

#### 2.3 Supabase Setup

In your Supabase project, create these **Storage Buckets**:

| Bucket Name | Public? | Content |
|-------------|---------|---------|
| `legal-pdfs` | ✅ Yes | State-wise Motor Vehicle Rules PDFs |
| `app-data` | ✅ Yes | `challans.json` file for offline sync |

Run this SQL in **Supabase SQL Editor** to create the PDFs table:

```sql
CREATE TABLE IF NOT EXISTS legal_pdfs (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    display_name TEXT,
    category TEXT DEFAULT 'State Law',
    state_name TEXT DEFAULT 'ALL',
    country TEXT DEFAULT 'India',
    file_url TEXT,
    file_size_bytes INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### 2.4 Pinecone Setup

Create a **Pinecone Index** with these settings:

| Setting | Value |
|---------|-------|
| Index Name | `roadlaw-legal` |
| Dimensions | `768` |
| Metric | `cosine` |
| Cloud | `aws` |
| Region | `us-east-1` |

#### 2.5 Run Backend Locally

```bash
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 3000
```

Backend will start at: `http://localhost:3000`

Test health: `http://localhost:3000/api/health`

---

### Step 3: Setup Android App

#### 3.1 Open in Android Studio

1. Open Android Studio
2. Click **"Open"** → Navigate to the cloned `Roadlawfull` folder → Click OK
3. Wait for Gradle sync to complete (it downloads dependencies automatically)

#### 3.2 File Locations in Android Studio

Once opened, these are the key files you'll see in the **Project** panel:

```
📁 Roadlawfull (Project Root)
└── 📁 app
    └── 📁 src
        └── 📁 main
            ├── 📄 AndroidManifest.xml          ← Permissions
            ├── 📁 assets
            │   └── 📄 index.html               ← ⭐ MAIN UI — edit this for frontend changes
            ├── 📁 java/com/bgi/roadlaw
            │   └── 📄 MainActivity.java         ← ⭐ NATIVE CODE — edit for Android features
            └── 📁 res
                ├── 📁 layout/activity_main.xml  ← WebView layout
                ├── 📁 values/strings.xml        ← App name
                └── 📁 mipmap-*/                 ← App icons
```

#### 3.3 Add your Groq API Key

Open `app/src/main/assets/index.html` and find **line 1321**:

```javascript
// BEFORE (placeholder):
const GROQ_API_KEY = 'YOUR_GROQ_API_KEY_HERE';

// AFTER (your real key):
const GROQ_API_KEY = 'gsk_your_actual_groq_api_key';
```

#### 3.4 Change Backend URL (Optional)

If running your own backend, find **line 1186** in `index.html`:

```javascript
// Default (uses our hosted server):
const DEFAULT_SERVER = 'https://roadlaw.onrender.com';

// Change to your own server:
const DEFAULT_SERVER = 'https://your-server.onrender.com';
// OR for local testing:
const DEFAULT_SERVER = 'http://YOUR_PC_IP:3000';
```

#### 3.5 Build & Run

1. Connect your Android phone via USB (enable USB debugging)
2. Click the **▶ Run** button in Android Studio
3. Select your device → App will install and launch
4. **Allow** Location and Notification permissions when prompted

---

### Step 4: Deploy Backend to Render (Cloud)

1. Push `new_app_backend` folder to a **separate GitHub repo**
2. Go to [render.com](https://render.com) → **New Web Service**
3. Connect your GitHub repo
4. Configure:

| Setting | Value |
|---------|-------|
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn server:app --host 0.0.0.0 --port $PORT` |

5. Add **Environment Variables** in Render dashboard:

| Key | Value |
|-----|-------|
| `GROQ_API_KEY` | Your Groq API key |
| `PINECONE_API_KEY` | Your Pinecone API key |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Your Supabase service key |
| `PYTHON_VERSION` | `3.11.9` |

6. Click **Deploy** → Wait for build → Your server will be live!

---

## 🔗 API Endpoints

Once backend is running, these endpoints are available:

### Core APIs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Server health check |
| `POST` | `/api/search` | AI legal search (RAG) |
| `POST` | `/api/calculator` | Challan fine calculator |

### Legal PDFs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/legal-pdfs/search?q=` | Search PDFs by name |
| `GET` | `/api/legal-pdfs/list` | List all PDFs |
| `POST` | `/api/legal-pdfs/upload` | Upload new PDF |
| `DELETE` | `/api/legal-pdfs/{id}` | Delete a PDF |

### Challan Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/sync-challans` | Download challans JSON |
| `GET` | `/api/calculator/stats` | Challan statistics |
| `GET` | `/api/calculator/health` | Calculator health |
| `POST` | `/api/admin/reload` | Reload challan data |
| `POST` | `/api/admin/add-challan` | Add new challan rule |
| `DELETE` | `/api/admin/clear-challans` | Clear all challans |

### Admin (PDF Ingestion to Pinecone)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/admin/ingest` | Upload & ingest PDF into vector DB |
| `POST` | `/api/admin/ingest-local` | Ingest from server path |
| `GET` | `/api/admin/pdfs` | List ingested PDFs |
| `GET` | `/api/admin/health` | Admin panel health |

---

## 🔧 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **App Shell** | Android (Java) + WebView | Native wrapper with GPS, downloads |
| **Frontend** | HTML + CSS + JavaScript | Single-page app UI |
| **Styling** | TailwindCSS + Material Symbols | Modern responsive design |
| **Backend** | Python FastAPI + Uvicorn | REST API server |
| **AI/LLM** | Groq (LLaMA 3) | Natural language answers |
| **Embeddings** | all-mpnet-base-v2 (768d) | Text → Vector conversion |
| **Vector DB** | Pinecone | Similarity search on legal docs |
| **Database** | Supabase (PostgreSQL) | PDF metadata storage |
| **File Storage** | Supabase Storage | PDF files + challans JSON |
| **Hosting** | Render (Free Tier) | Backend cloud deployment |

---

## 📱 Android Permissions

| Permission | Why Needed |
|-----------|------------|
| `INTERNET` | API calls to backend server |
| `ACCESS_NETWORK_STATE` | Check online/offline status |
| `ACCESS_FINE_LOCATION` | GPS → Detect user's state |
| `ACCESS_COARSE_LOCATION` | Approximate location fallback |
| `POST_NOTIFICATIONS` | Show download progress (Android 13+) |
| `WRITE_EXTERNAL_STORAGE` | Save PDFs to Downloads (Android ≤ 9) |

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| AI Assistant not responding | Check if Groq API key is added in `index.html` line 1321 |
| "Cannot reach server" error | Backend might be sleeping (free tier). Wait 15 seconds and try again |
| PDFs not downloading | Allow notification permission in phone settings |
| Location not detected | Allow location permission → Restart app |
| Offline challan shows 0 | Click "Sync Offline Data" in Profile page first |
| Render memory exceeded | Make sure `requirements.txt` has CPU-only torch |
| Build fails in Android Studio | Sync Gradle → Clean Project → Rebuild |

---

## 📜 License

This project is for educational purposes.

---

<p align="center">
  <b>Made with ❤️ for Indian Drivers</b><br/>
  <i>Stay safe. Follow traffic rules. 🚦</i>
</p>
