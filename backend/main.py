"""
Playfair Cipher — FastAPI Backend
==================================
Exposes two endpoints:
  POST /cipher   → encrypt or decrypt a message with full step-by-step logs
  GET  /health   → simple liveness check

Run with:
  pip install fastapi uvicorn
  uvicorn main:app --reload
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal

app = FastAPI(title="Playfair Cipher API", version="1.0.0")

# Allow the Vite dev server (and any local origin) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten this in production
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────────────────────────

class CipherRequest(BaseModel):
    keyword: str         # The secret keyword used to build the key square
    message: str         # Plaintext (for encrypt) or ciphertext (for decrypt)
    mode: Literal["encrypt", "decrypt"]


class Coords(BaseModel):
    row: int
    col: int


class StepCoords(BaseModel):
    a:  Coords   # first input letter position
    b:  Coords   # second input letter position
    a2: Coords   # first output letter position
    b2: Coords   # second output letter position


class Step(BaseModel):
    input_pair:  str          # e.g. "HE"
    output_pair: str          # e.g. "BN"
    rule:        str          # "ROW" | "COL" | "BOX"
    description: str          # human-readable explanation
    coords:      StepCoords   # grid coordinates for visualization


class CipherResponse(BaseModel):
    result:          str          # final ciphertext or plaintext
    grid:            list[list[str]]  # 5×5 key square
    digraph_display: str          # space-separated digraph pairs (e.g. "HE LL OX")
    steps:           list[Step]   # per-digraph explanation


# ── Playfair Core Logic ───────────────────────────────────────────────────────

def build_key_square(keyword: str) -> list[list[str]]:
    """
    Build a 5×5 Playfair key square from the given keyword.

    Algorithm:
    1. Uppercase and remove non-alphabetic characters from the keyword.
    2. Treat I and J as the same letter (replace J → I).
    3. Walk the keyword, adding each unseen letter to the square in order.
    4. Fill remaining positions with the rest of the alphabet (A–Z, skipping J
       and any letters already added from the keyword).
    5. Arrange the 25 letters into a 5×5 grid row by row.
    """
    seen: set[str] = set()
    letters: list[str] = []

    # Process keyword characters
    for ch in keyword.upper():
        if not ch.isalpha():
            continue
        ch = ch.replace("J", "I")  # merge I and J
        if ch not in seen:
            seen.add(ch)
            letters.append(ch)

    # Fill with the remaining alphabet (A–Z, no J)
    for code in range(ord("A"), ord("Z") + 1):
        ch = chr(code)
        if ch == "J":
            continue
        if ch not in seen:
            seen.add(ch)
            letters.append(ch)

    # Arrange into 5 rows of 5
    return [letters[r * 5 : r * 5 + 5] for r in range(5)]


def build_pos_map(grid: list[list[str]]) -> dict[str, tuple[int, int]]:
    """
    Create a letter → (row, col) lookup dictionary from the key square.
    Allows O(1) coordinate look-up during cipher processing.
    """
    pos: dict[str, tuple[int, int]] = {}
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            pos[ch] = (r, c)
    return pos


def prepare_digraphs(text: str) -> list[tuple[str, str]]:
    """
    Convert raw plaintext/ciphertext into a list of digraph pairs.

    Rules applied in order:
    1. Uppercase, replace J→I, strip non-alpha characters.
    2. Walk the character list two at a time:
       - If both letters of a prospective pair are the same, insert 'X' as a
         filler between them (to break up the double) and reprocess.
    3. If the total character count is odd after the above, append a trailing 'X'.
    4. Split the resulting list into consecutive pairs.
    """
    # Step 1: clean the text
    clean = (
        text.upper()
        .replace("J", "I")
    )
    clean = "".join(ch for ch in clean if ch.isalpha())

    # Step 2: insert X fillers between identical adjacent letters
    chars: list[str] = []
    i = 0
    while i < len(clean):
        chars.append(clean[i])
        if i + 1 < len(clean):
            if clean[i] == clean[i + 1]:
                # Same-letter pair — insert filler before consuming the second letter
                chars.append("X")
            else:
                chars.append(clean[i + 1])
                i += 1  # consumed two letters
        i += 1

    # Step 3: pad to even length
    if len(chars) % 2 != 0:
        chars.append("X")

    # Step 4: split into pairs
    return [(chars[j], chars[j + 1]) for j in range(0, len(chars), 2)]


def process_digraph(
    a: str,
    b: str,
    grid: list[list[str]],
    pos_map: dict[str, tuple[int, int]],
    direction: int,  # +1 = encrypt, -1 = decrypt
) -> Step:
    """
    Apply the appropriate Playfair rule to a single digraph (a, b) and return
    a Step describing what happened.

    The three rules:
    ┌──────────────────────────────────────────────────────────────────────────┐
    │ ROW   Both letters share the same ROW.                                   │
    │       Encrypt: shift each letter's column one step to the RIGHT.         │
    │       Decrypt: shift each letter's column one step to the LEFT.          │
    │       Wraps around (modulo 5).                                           │
    ├──────────────────────────────────────────────────────────────────────────┤
    │ COL   Both letters share the same COLUMN.                                │
    │       Encrypt: shift each letter's row one step DOWN.                    │
    │       Decrypt: shift each letter's row one step UP.                      │
    │       Wraps around (modulo 5).                                           │
    ├──────────────────────────────────────────────────────────────────────────┤
    │ BOX   Letters are at opposite corners of a rectangle on the grid.        │
    │       Each letter is replaced by the letter at the SAME ROW but the      │
    │       OTHER letter's COLUMN (i.e., swap corners horizontally).            │
    │       Direction makes no difference for the box rule.                    │
    └──────────────────────────────────────────────────────────────────────────┘
    """
    ra, ca = pos_map[a]
    rb, cb = pos_map[b]

    if ra == rb:
        # ── Same Row ──────────────────────────────────────────────────────────
        rule = "ROW"
        ca2 = (ca + direction) % 5
        cb2 = (cb + direction) % 5
        a2 = grid[ra][ca2]
        b2 = grid[rb][cb2]
        desc = (
            f"Both '{a}' and '{b}' are in row {ra + 1}. "
            f"{'Shift columns right →' if direction == 1 else 'Shift columns left ←'}: "
            f"'{a}' ({ra+1},{ca+1}) → '{a2}' ({ra+1},{ca2+1}), "
            f"'{b}' ({rb+1},{cb+1}) → '{b2}' ({rb+1},{cb2+1})."
        )
        coords = StepCoords(
            a=Coords(row=ra, col=ca), b=Coords(row=rb, col=cb),
            a2=Coords(row=ra, col=ca2), b2=Coords(row=rb, col=cb2),
        )

    elif ca == cb:
        # ── Same Column ───────────────────────────────────────────────────────
        rule = "COL"
        ra2 = (ra + direction) % 5
        rb2 = (rb + direction) % 5
        a2 = grid[ra2][ca]
        b2 = grid[rb2][cb]
        desc = (
            f"Both '{a}' and '{b}' are in column {ca + 1}. "
            f"{'Shift rows down ↓' if direction == 1 else 'Shift rows up ↑'}: "
            f"'{a}' ({ra+1},{ca+1}) → '{a2}' ({ra2+1},{ca+1}), "
            f"'{b}' ({rb+1},{cb+1}) → '{b2}' ({rb2+1},{cb+1})."
        )
        coords = StepCoords(
            a=Coords(row=ra, col=ca), b=Coords(row=rb, col=cb),
            a2=Coords(row=ra2, col=ca), b2=Coords(row=rb2, col=cb),
        )

    else:
        # ── Rectangle / Box Rule ──────────────────────────────────────────────
        rule = "BOX"
        a2 = grid[ra][cb]   # same row as 'a', column of 'b'
        b2 = grid[rb][ca]   # same row as 'b', column of 'a'
        a2r, a2c = pos_map[a2]
        b2r, b2c = pos_map[b2]
        desc = (
            f"'{a}' ({ra+1},{ca+1}) and '{b}' ({rb+1},{cb+1}) form a rectangle. "
            f"Swap corners: '{a}' → '{a2}' ({a2r+1},{a2c+1}), "
            f"'{b}' → '{b2}' ({b2r+1},{b2c+1})."
        )
        coords = StepCoords(
            a=Coords(row=ra, col=ca), b=Coords(row=rb, col=cb),
            a2=Coords(row=a2r, col=a2c), b2=Coords(row=b2r, col=b2c),
        )

    return Step(
        input_pair=a + b,
        output_pair=a2 + b2,
        rule=rule,
        description=desc,
        coords=coords,
    )


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok"}


@app.post("/cipher", response_model=CipherResponse)
def cipher(req: CipherRequest) -> CipherResponse:
    """
    Encrypt or decrypt *message* using the Playfair cipher with *keyword*.

    Request body:
      {
        "keyword": "MONARCHY",
        "message": "HELLO WORLD",
        "mode":    "encrypt"    // or "decrypt"
      }

    Response:
      {
        "result":          "CFASRPtap",
        "grid":            [["M","O","N","A","R"], ...],
        "digraph_display": "HE LX LO WO RL D",
        "steps":           [ { input_pair, output_pair, rule, description, coords }, ... ]
      }
    """
    # ── Validate inputs ───────────────────────────────────────────────────────
    if not req.keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty.")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # ── Build cipher structures ───────────────────────────────────────────────
    grid = build_key_square(req.keyword)
    pos_map = build_pos_map(grid)
    direction = 1 if req.mode == "encrypt" else -1

    # ── Prepare digraph pairs ─────────────────────────────────────────────────
    pairs = prepare_digraphs(req.message)
    if not pairs:
        raise HTTPException(
            status_code=400,
            detail="No valid alphabetic characters found in message.",
        )

    # ── Process each digraph and collect steps ────────────────────────────────
    steps: list[Step] = [
        process_digraph(a, b, grid, pos_map, direction)
        for a, b in pairs
    ]

    # ── Assemble final result and display string ──────────────────────────────
    result = "".join(s.output_pair for s in steps)
    digraph_display = " ".join(s.input_pair for s in steps)

    return CipherResponse(
        result=result,
        grid=grid,
        digraph_display=digraph_display,
        steps=steps,
    )
