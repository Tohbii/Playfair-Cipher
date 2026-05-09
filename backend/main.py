# ── Playfair Cipher Backend ───────────────────────────────────────────────────
# FastAPI server with zero pydantic dependency.
# Works on any Python version (tested on 3.11–3.14).
#
# Endpoints:
#   GET  /health  → liveness check
#   POST /cipher  → encrypt or decrypt with full step-by-step logs
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow the React frontend (any origin) to call this API.
# Tighten allow_origins to your Vercel URL in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Core Cipher Functions ─────────────────────────────────────────────────────

def build_key_square(keyword):
    """
    Build a 5x5 Playfair key square from the given keyword.

    Steps:
    1. Uppercase and remove non-alpha characters.
    2. Replace J with I (I and J share one cell in Playfair).
    3. Add each unseen keyword letter to the square in order.
    4. Fill remaining cells with the rest of the alphabet (A-Z, no J).
    5. Arrange the 25 letters into 5 rows of 5.
    """
    seen, letters = set(), []

    for ch in keyword.upper():
        if not ch.isalpha():
            continue
        ch = "I" if ch == "J" else ch   # merge J into I
        if ch not in seen:
            seen.add(ch)
            letters.append(ch)

    # Fill with remaining alphabet, skipping J
    for code in range(65, 91):
        ch = chr(code)
        if ch == "J":
            continue
        if ch not in seen:
            seen.add(ch)
            letters.append(ch)

    # Pack into 5 rows of 5
    return [letters[r * 5: r * 5 + 5] for r in range(5)]


def build_pos_map(grid):
    """
    Build a letter -> (row, col) lookup dictionary from the key square.
    Allows O(1) coordinate lookup during cipher processing.
    """
    return {grid[r][c]: (r, c) for r in range(5) for c in range(5)}


def prepare_digraphs(text):
    """
    Convert raw text into a list of digraph (letter pair) tuples.

    Rules applied in order:
    1. Uppercase, replace J->I, strip non-alpha characters.
    2. If both letters in a prospective pair are the same, insert X between them.
    3. If the total character count is odd, pad with a trailing X.
    4. Split into consecutive pairs.

    Example: "HELLO" -> [("HE"), ("LX"), ("LO")]
             (X inserted between the double L)
    """
    # Step 1: clean the input
    clean = "".join(
        ("I" if c == "J" else c)
        for c in text.upper()
        if c.isalpha()
    )

    # Step 2: insert X fillers between identical adjacent letters
    chars, i = [], 0
    while i < len(clean):
        chars.append(clean[i])
        if i + 1 < len(clean):
            if clean[i] == clean[i + 1]:
                chars.append("X")       # filler between double letters
            else:
                chars.append(clean[i + 1])
                i += 1                  # consumed two letters
        i += 1

    # Step 3: pad to even length
    if len(chars) % 2:
        chars.append("X")

    # Step 4: split into pairs
    return [(chars[j], chars[j + 1]) for j in range(0, len(chars), 2)]


def process_digraph(a, b, grid, pos_map, direction):
    """
    Apply the correct Playfair rule to a single digraph (a, b).
    direction: +1 = encrypt, -1 = decrypt

    The three rules:
    ┌─────────────────────────────────────────────────────────────────┐
    │ ROW  Both letters share the same ROW.                           │
    │      Encrypt: shift each column one step RIGHT (wraps at 5).   │
    │      Decrypt: shift each column one step LEFT  (wraps at 5).   │
    ├─────────────────────────────────────────────────────────────────┤
    │ COL  Both letters share the same COLUMN.                        │
    │      Encrypt: shift each row one step DOWN  (wraps at 5).      │
    │      Decrypt: shift each row one step UP    (wraps at 5).      │
    ├─────────────────────────────────────────────────────────────────┤
    │ BOX  Letters are at opposite corners of a rectangle.            │
    │      Each letter moves to the same row but the other           │
    │      letter's column (swap corners horizontally).               │
    │      Direction makes no difference for the box rule.            │
    └─────────────────────────────────────────────────────────────────┘

    Returns a dict with the input/output pair, rule name, human
    description, and grid coordinates for frontend highlighting.
    """
    ra, ca = pos_map[a]
    rb, cb = pos_map[b]

    if ra == rb:
        # ── Same Row ──────────────────────────────────────────────────
        ca2 = (ca + direction) % 5
        cb2 = (cb + direction) % 5
        a2  = grid[ra][ca2]
        b2  = grid[rb][cb2]
        rule = "ROW"
        desc = (
            f"Same row {ra+1}: shift {'right' if direction == 1 else 'left'}. "
            f"'{a}'→'{a2}', '{b}'→'{b2}'."
        )
        coords = {
            "a":  {"row": ra, "col": ca},
            "b":  {"row": rb, "col": cb},
            "a2": {"row": ra, "col": ca2},
            "b2": {"row": rb, "col": cb2},
        }

    elif ca == cb:
        # ── Same Column ───────────────────────────────────────────────
        ra2 = (ra + direction) % 5
        rb2 = (rb + direction) % 5
        a2  = grid[ra2][ca]
        b2  = grid[rb2][cb]
        rule = "COL"
        desc = (
            f"Same column {ca+1}: shift {'down' if direction == 1 else 'up'}. "
            f"'{a}'→'{a2}', '{b}'→'{b2}'."
        )
        coords = {
            "a":  {"row": ra,  "col": ca},
            "b":  {"row": rb,  "col": cb},
            "a2": {"row": ra2, "col": ca},
            "b2": {"row": rb2, "col": cb},
        }

    else:
        # ── Rectangle / Box Rule ──────────────────────────────────────
        a2 = grid[ra][cb]   # same row as a, column of b
        b2 = grid[rb][ca]   # same row as b, column of a
        a2r, a2c = pos_map[a2]
        b2r, b2c = pos_map[b2]
        rule = "BOX"
        desc = (
            f"Rectangle: '{a}'({ra+1},{ca+1})→'{a2}', "
            f"'{b}'({rb+1},{cb+1})→'{b2}'."
        )
        coords = {
            "a":  {"row": ra,  "col": ca},
            "b":  {"row": rb,  "col": cb},
            "a2": {"row": a2r, "col": a2c},
            "b2": {"row": b2r, "col": b2c},
        }

    return {
        "input_pair":  a + b,
        "output_pair": a2 + b2,
        "rule":        rule,
        "description": desc,
        "coords":      coords,
    }


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Simple liveness probe — useful for Render's health check."""
    return {"status": "ok"}


@app.post("/cipher")
def cipher(body: dict):
    """
    Encrypt or decrypt a message using the Playfair cipher.

    Request body (JSON):
      {
        "keyword": "MONARCHY",
        "message": "HELLO WORLD",
        "mode":    "encrypt"     // or "decrypt"
      }

    Response:
      {
        "result":          "CFASRP...",
        "grid":            [["M","O","N","A","R"], ...],
        "digraph_display": "HE LX LO WO RL D",
        "steps":           [ { input_pair, output_pair, rule, description, coords }, ... ]
      }
    """
    # Extract and validate inputs
    keyword = body.get("keyword", "").strip()
    message = body.get("message", "").strip()
    mode    = body.get("mode", "encrypt")

    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty.")
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Build the key square and position map
    grid    = build_key_square(keyword)
    pos_map = build_pos_map(grid)

    # Prepare digraph pairs from the input message
    pairs = prepare_digraphs(message)
    if not pairs:
        raise HTTPException(status_code=400, detail="No valid letters in message.")

    # Process each digraph with the correct direction
    direction = 1 if mode == "encrypt" else -1
    steps = [process_digraph(a, b, grid, pos_map, direction) for a, b in pairs]

    return {
        "result":          "".join(s["output_pair"] for s in steps),
        "grid":            grid,
        "digraph_display": " ".join(s["input_pair"] for s in steps),
        "steps":           steps,
    }