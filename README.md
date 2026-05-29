# 🚗 Roadlaw - AI Traffic Law Assistant

An Android app that helps Indian drivers understand traffic laws, calculate challans, and access state-specific legal documents.

## ✨ Features

- **🤖 AI Legal Assistant** — Ask traffic law questions in English or Hindi. Uses RAG (Retrieval-Augmented Generation) to give state-specific answers based on actual legal documents.
- **💰 Challan Calculator** — Enter your violation and get the exact fine amount. Works both online and offline.
- **📄 Legal PDFs** — Browse and download state-wise Motor Vehicle Rules PDFs.
- **📍 GPS Location Detection** — Automatically detects your state and shows relevant laws.
- **📶 Offline Mode** — Challan calculator works without internet using cached data.

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Android WebView + HTML/CSS/JS |
| Backend | Python FastAPI |
| AI Model | Groq (LLaMA) |
| Embeddings | Sentence Transformers (all-mpnet-base-v2) |
| Vector DB | Pinecone |
| Database | Supabase (PostgreSQL) + MongoDB |
| Hosting | Render |

## 📁 Project Structure

```
ROADSAFTEY/
├── app/                        # Android app source
│   └── src/main/
│       ├── assets/index.html   # Main UI (single-page app)
│       └── java/.../MainActivity.java
├── new_app_backend/            # Backend server
│   ├── server.py               # FastAPI server (unified)
│   ├── ss2_engine.py           # RAG search engine
│   ├── challan_engine.py       # Challan calculator engine
│   └── requirements.txt
├── challan/                    # Old challan scripts
├── build.gradle.kts
└── settings.gradle.kts
```

## ⚠️ API Key Setup (Important!)

Before running the app, you need to add your **Groq API Key** in the following file:

### 📱 App (Frontend)
File: `app/src/main/assets/index.html`  
Find this line (around line 1321):
```javascript
const GROQ_API_KEY = 'YOUR_GROQ_API_KEY_HERE';
```
Replace `YOUR_GROQ_API_KEY_HERE` with your actual Groq API key.

> 🔑 Get your free Groq API key at: [https://console.groq.com](https://console.groq.com)

### 🖥️ Backend
File: `new_app_backend/.env`  
Create a `.env` file with the following variables:
```env
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_supabase_key
PINECONE_API_KEY=your_pinecone_key
GROQ_API_KEY=your_groq_key
MONGO_URI=your_mongodb_uri
```

> See `new_app_backend/.env.example` for reference.

## 🚀 How to Run

### Backend
```bash
cd new_app_backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 3000
```

### Android App
1. Open the project in Android Studio
2. Add your Groq API key in `index.html`
3. Build and run on your device/emulator

## 📜 License

This project is for educational purposes.
