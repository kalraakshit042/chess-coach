# ♞ Chess Coach

An AI-powered chess coaching web app that analyzes your Lichess game history. Enter your username, and Chess Coach fetches your rated games, identifies your opening repertoire, and delivers detailed coaching on accuracy, tactics, and positional play — powered by Claude and Stockfish.

> Built for club players who want specific, actionable feedback on their openings — not generic engine output.

---

## Features

- **Opening Repertoire Detection** — groups your games by ECO code, filters to openings with 3+ games
- **Stockfish Engine Analysis** — calculates Average Centipawn Loss (ACPL) and flags tactical blunders
- **Claude AI Coaching** — generates natural language analysis: accuracy, tactics, positional themes, and one concrete recommendation per opening
- **Interactive Chess Board** — view key positions from your games directly in the app
- **Streaming Progress** — real-time updates as analysis runs (fetching → engine → AI coaching)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + Tailwind CSS |
| Backend | Python + FastAPI |
| Chess Logic | python-chess + Stockfish |
| AI Analysis | [Claude API](https://docs.anthropic.com) (claude-sonnet-4-20250514) |
| Game Data | Lichess Public API (no key required) |

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Stockfish binary installed
- An Anthropic API key

### 1. Install Stockfish

**macOS:**
```bash
brew install stockfish
```

**Ubuntu/Debian:**
```bash
sudo apt install stockfish
```

**Windows:** Download from [stockfishchess.org](https://stockfishchess.org/download/) and add to PATH.

### 2. Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set your API key
cp ../.env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Start the server
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Visit `/docs` for the interactive API docs.

### 3. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key from [console.anthropic.com](https://console.anthropic.com) |

---

## Project Structure

```
chess-coach/
├── backend/
│   ├── main.py           # FastAPI app, endpoints
│   ├── lichess.py        # Lichess API integration & PGN parsing
│   ├── analysis.py       # Stockfish evaluation, ACPL, tactical detection
│   ├── claude_coach.py   # Claude API coaching prompts
│   ├── models.py         # Pydantic data models
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── UsernameInput.jsx
│   │   │   ├── LoadingState.jsx
│   │   │   ├── RepertoireView.jsx
│   │   │   ├── OpeningCard.jsx
│   │   │   └── ChessBoard.jsx
│   │   └── utils/api.js
│   ├── package.json
│   └── vite.config.js
├── .env.example
└── README.md
```

---

## Usage Notes

- **Private accounts:** The Lichess API only returns games from public accounts.
- **Rate limits:** Lichess allows 1 req/sec for game exports. The app automatically respects this.
- **Stockfish:** If Stockfish isn't installed, analysis still runs — Claude uses move sequences instead of engine evals.
- **Analysis time:** Expect 1–3 minutes for a full analysis depending on game count and number of openings.

---

## Disclaimer

Analysis powered by Claude AI and Stockfish. For educational purposes only. Results reflect patterns in historical games and should be used as a starting point for study, not as definitive evaluations.

---

## Built With

[![Anthropic Claude](https://img.shields.io/badge/Built%20with-Claude%20API-orange?style=flat-square)](https://docs.anthropic.com)

Built by [Akshit Kalra](https://www.akshitkalra.com/)
