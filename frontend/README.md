# Playfair Cipher — Full-Stack App

A full-stack demonstration of the Playfair Cipher with step-by-step transparency.

## Stack

| Layer    | Technology                              |
|----------|-----------------------------------------|
| Backend  | Python 3.11+ · FastAPI · Uvicorn        |
| Frontend | React 18 · Vite · Tailwind CSS · Axios  |

---

## Quick Start

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
# → API running at http://localhost:8000
# → Docs at      http://localhost:8000/docs
```

### 2. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
# → App running at http://localhost:5173
```

---

## API Reference

### POST /cipher

**Request**
```json
{
  "keyword": "MONARCHY",
  "message": "HELLO WORLD",
  "mode":    "encrypt"
}
```

**Response**
```json
{
  "result": "CFASRP...",
  "grid": [["M","O","N","A","R"], ...],
  "digraph_display": "HE LX LO WO RL D",
  "steps": [
    {
      "input_pair":  "HE",
      "output_pair": "BN",
      "rule":        "BOX",
      "description": "'H' (1,3) and 'E' (4,1) form a rectangle. Swap corners: ...",
      "coords": {
        "a":  { "row": 0, "col": 2 },
        "b":  { "row": 3, "col": 0 },
        "a2": { "row": 0, "col": 0 },
        "b2": { "row": 3, "col": 2 }
      }
    },
    ...
  ]
}
```

---

## Playfair Cipher Rules

| Rule      | Condition              | Encrypt             | Decrypt             |
|-----------|------------------------|---------------------|---------------------|
| Row       | Same row               | Shift column right  | Shift column left   |
| Column    | Same column            | Shift row down      | Shift row up        |
| Rectangle | Different row & column | Swap row corners    | Swap row corners    |

**Digraph preparation rules:**
1. Uppercase all letters; replace J → I; strip non-alpha.
2. If a pair would contain the same letter twice, insert X between them.
3. Pad with a trailing X if the total character count is odd.
