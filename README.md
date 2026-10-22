# ArchScrape

ArchScrape is an automated company intelligence and lead discovery platform for architecture and interior design practices. Built with a React + TypeScript frontend and a FastAPI backend powered by Firecrawl, Google Places, and OpenRouter AI.

- **Live Web App:** [https://archscrape.vercel.app](https://archscrape.vercel.app)
- **Live API:** [https://archscrape.onrender.com](https://archscrape.onrender.com)

---

## Prerequisites

- **Node.js** 18+ & `npm`
- **Python** 3.11+
- API Keys:
  - [Firecrawl API Key](https://firecrawl.dev)
  - [OpenRouter API Key](https://openrouter.ai)
  - [Google Places API Key](https://console.cloud.google.com/) *(optional)*

---

## Quick Setup

### 1. Clone the Repository

```bash
git clone https://github.com/manishns2007/ArchScrape.git
cd ArchScrape
```

### 2. Backend Setup (FastAPI)

1. Create and activate a Python virtual environment:
   ```bash
   # Windows
   py -m venv .venv
   .venv\Scripts\activate

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables in `.env` (project root):
   ```env
   FIRECRAWL_API_KEY=your_firecrawl_api_key
   OPENROUTER_API_KEY=your_openrouter_api_key
   GOOGLE_PLACES_API_KEY=your_google_places_api_key
   OPENROUTER_MODEL=google/gemini-2.5-flash
   OPENROUTER_FALLBACK_MODEL=meta-llama/llama-3.3-70b-instruct
   CORS_ORIGINS=http://localhost:5173,https://archscrape.vercel.app
   ```

4. Start the backend server:
   ```bash
   uvicorn server:app --host 127.0.0.1 --port 8000 --reload
   ```
   *API will run at `http://127.0.0.1:8000` (docs at `http://127.0.0.1:8000/docs`).*

---

### 3. Frontend Setup (React + Vite)

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   npm install
   ```

2. *(Optional)* Configure local environment in `frontend/.env`:
   ```env
   VITE_API_URL=http://127.0.0.1:8000
   ```

3. Start the frontend development server:
   ```bash
   npm run dev
   ```
   *App will open at `http://localhost:5173`.*

---

## Production Deployment

- **Frontend (Vercel):** Configured with root [`vercel.json`](./vercel.json) and deployed via `vercel --prod` with `VITE_API_URL=https://archscrape.onrender.com`.
- **Backend (Render):** Managed via [`render.yaml`](./render.yaml) as a Free Plan Web Service (`uvicorn server:app --host 0.0.0.0 --port $PORT`).

---

## Testing

```bash
# Run backend test suite
pytest tests/ -v
```
