# StoryVox

**Turn any epub into a fully-voiced radio play.**

Multi-voice TTS, AI screenplay conversion with Writer/Director feedback loop, sound effects, dramatic stingers — all in a beautiful web player.

## Architecture

```
storyvox/
├── frontend/    → Next.js 14 (deploy to Vercel)
└── server/      → FastAPI (deploy to Render)
```

## Quick Start

### Frontend
```bash
cd frontend
npm install
npm run dev       # → http://localhost:3000
```

### Backend
```bash
cd server
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Environment Variables

**Frontend** (`frontend/.env.local`):
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Backend** (`server/.env`):
```
DATABASE_URL=postgresql://user:pass@host/storyvox
GEMINI_API_KEY=your-gemini-key
GROQ_API_KEY=optional
CLOUDFLARE_R2_ACCESS_KEY=optional
CLOUDFLARE_R2_SECRET_KEY=optional
CLOUDFLARE_R2_BUCKET=storyvox
CLOUDFLARE_R2_ENDPOINT=https://xxx.r2.cloudflarestorage.com
```

## Deployment

### Vercel (Frontend)
1. Connect GitHub repo
2. Set root directory to `frontend`
3. Add env: `NEXT_PUBLIC_API_URL=https://your-render-url.onrender.com`

### Render (Backend)
1. Connect GitHub repo
2. Set root directory to `server`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables from above
