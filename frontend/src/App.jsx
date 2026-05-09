/**
 * App.jsx — Playfair Cipher Frontend
 * ====================================
 * Communicates with the FastAPI backend at http://localhost:8000/cipher.
 *
 * Features:
 *  • Keyword input → live key-square preview
 *  • Plaintext / ciphertext textarea
 *  • Encrypt / Decrypt buttons
 *  • 5×5 grid display with per-step letter highlighting
 *  • Step-by-step explanation panel (click a step → highlights on grid)
 */

import { useState, useEffect, useCallback } from "react";
import axios from "axios";

// ── Constants ────────────────────────────────────────────────────────────────

const API_URL = "https://playfair-cipher-gv91.onrender.com";

/** Build key square client-side for the live preview (mirrors Python logic). */
function buildKeySquare(keyword) {
  const seen = new Set();
  const letters = [];

  for (const ch of keyword.toUpperCase()) {
    if (!/[A-Z]/.test(ch)) continue;
    const c = ch === "J" ? "I" : ch;
    if (!seen.has(c)) { seen.add(c); letters.push(c); }
  }
  for (let i = 65; i <= 90; i++) {
    const c = String.fromCharCode(i);
    if (c === "J") continue;
    if (!seen.has(c)) { seen.add(c); letters.push(c); }
  }

  const grid = [];
  for (let r = 0; r < 5; r++) grid.push(letters.slice(r * 5, r * 5 + 5));
  return grid;
}

// ── Rule badge colours (Tailwind) ────────────────────────────────────────────
const RULE_STYLES = {
  ROW: "bg-blue-100 text-blue-800",
  COL: "bg-green-100 text-green-800",
  BOX: "bg-pink-100  text-pink-800",
};
const RULE_LABELS = { ROW: "Same Row", COL: "Same Col", BOX: "Rectangle" };

// ── KeySquare component ───────────────────────────────────────────────────────

/**
 * Renders the 5×5 Playfair key square.
 * @param {string[][]} grid       - 2-D array of letters
 * @param {object|null} highlight - { origSet, resSet } of "row,col" strings to colour
 */
function KeySquare({ grid, highlight }) {
  if (!grid || grid.length === 0) return null;

  const origSet = highlight?.origSet ?? new Set();
  const resSet  = highlight?.resSet  ?? new Set();

  return (
    <div className="grid grid-cols-5 gap-1">
      {grid.map((row, r) =>
        row.map((letter, c) => {
          const key = `${r},${c}`;
          let bg = "bg-gray-50 text-gray-700 border-gray-200";
          if (resSet.has(key))  bg = "bg-emerald-500 text-white border-emerald-500";
          else if (origSet.has(key)) bg = "bg-blue-500  text-white border-blue-500";

          return (
            <div
              key={`${r}-${c}`}
              className={`flex items-center justify-center aspect-square border rounded text-base font-mono font-medium transition-colors duration-200 ${bg}`}
            >
              {letter}
            </div>
          );
        })
      )}
    </div>
  );
}

// ── StepList component ────────────────────────────────────────────────────────

/**
 * Renders the ordered list of digraph steps.
 * Clicking a step calls onSelect(stepIndex) so the parent can highlight the grid.
 */
function StepList({ steps, activeIndex, onSelect }) {
  if (!steps || steps.length === 0) return null;

  return (
    <div className="space-y-2">
      {steps.map((step, i) => {
        const isActive = i === activeIndex;
        return (
          <button
            key={i}
            onClick={() => onSelect(isActive ? null : i)}
            className={`w-full text-left px-3 py-2.5 rounded-lg border transition-colors duration-100 flex items-start gap-3
              ${isActive
                ? "bg-gray-50 border-gray-400"
                : "bg-white border-gray-200 hover:bg-gray-50"}`}
          >
            {/* Digraph pair */}
            <span className="font-mono font-semibold text-gray-900 text-base min-w-[64px]">
              {step.input_pair} → {step.output_pair}
            </span>

            {/* Rule badge */}
            <span className={`text-xs font-semibold px-2 py-0.5 rounded ml-auto shrink-0 ${RULE_STYLES[step.rule]}`}>
              {RULE_LABELS[step.rule]}
            </span>

            {/* Human description */}
            <span className="text-xs text-gray-500 leading-snug hidden sm:block">
              {step.description}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [keyword, setKeyword]         = useState("MONARCHY");
  const [message, setMessage]         = useState("HELLO WORLD");
  const [mode, setMode]               = useState("encrypt");

  const [grid, setGrid]               = useState(() => buildKeySquare("MONARCHY"));
  const [result, setResult]           = useState("");
  const [steps, setSteps]             = useState([]);
  const [digraphDisplay, setDigraph]  = useState("");
  const [activeStep, setActiveStep]   = useState(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState("");

  // Live-preview the key square whenever the keyword changes
  useEffect(() => {
    if (keyword.trim()) {
      setGrid(buildKeySquare(keyword));
      setActiveStep(null);  // clear highlights on keyword change
    }
  }, [keyword]);

  /** Compute the cell-highlight sets for the currently selected step. */
  const getHighlight = useCallback(() => {
    if (activeStep === null || !steps[activeStep]) return null;
    const { coords } = steps[activeStep];
    return {
      origSet: new Set([`${coords.a.row},${coords.a.col}`, `${coords.b.row},${coords.b.col}`]),
      resSet:  new Set([`${coords.a2.row},${coords.a2.col}`, `${coords.b2.row},${coords.b2.col}`]),
    };
  }, [activeStep, steps]);

  /** POST to the FastAPI backend and update state from the response. */
  const runCipher = async (selectedMode) => {
    setError("");
    setLoading(true);
    setResult("");
    setSteps([]);
    setDigraph("");
    setActiveStep(null);

    try {
      const { data } = await axios.post(API_URL, {
        keyword,
        message,
        mode: selectedMode,
      });

      setGrid(data.grid);               // use server-generated grid
      setResult(data.result);
      setSteps(data.steps);
      setDigraph(data.digraph_display);
      setMode(selectedMode);
    } catch (err) {
      const detail = err.response?.data?.detail ?? err.message;
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-4xl mx-auto">

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <header className="mb-8 border-b border-gray-200 pb-4">
          <h1 className="text-2xl font-mono font-semibold tracking-widest text-gray-900">
            PLAYFAIR CIPHER
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            5×5 key square · digraph substitution · step-by-step transparency
          </p>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

          {/* ── Left column: inputs + result ─────────────────────────────── */}
          <div className="space-y-5">

            {/* Keyword */}
            <div>
              <label className="block text-xs font-semibold tracking-widest text-gray-500 mb-1 uppercase">
                Keyword
              </label>
              <input
                type="text"
                value={keyword}
                onChange={e => setKeyword(e.target.value)}
                className="w-full font-mono border border-gray-300 rounded-lg px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
                placeholder="e.g. MONARCHY"
              />
            </div>

            {/* Message */}
            <div>
              <label className="block text-xs font-semibold tracking-widest text-gray-500 mb-1 uppercase">
                Message
              </label>
              <textarea
                value={message}
                onChange={e => setMessage(e.target.value)}
                rows={4}
                className="w-full font-mono border border-gray-300 rounded-lg px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white resize-y"
                placeholder="Enter plaintext or ciphertext..."
              />
            </div>

            {/* Action buttons */}
            <div className="flex gap-3">
              <button
                onClick={() => runCipher("encrypt")}
                disabled={loading}
                className="flex-1 bg-gray-900 text-white font-mono font-semibold py-2 rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors tracking-wider"
              >
                {loading && mode === "encrypt" ? "..." : "ENCRYPT"}
              </button>
              <button
                onClick={() => runCipher("decrypt")}
                disabled={loading}
                className="flex-1 border border-gray-900 text-gray-900 font-mono font-semibold py-2 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition-colors tracking-wider"
              >
                {loading && mode === "decrypt" ? "..." : "DECRYPT"}
              </button>
            </div>

            {/* Error */}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            {/* Result */}
            <div>
              <label className="block text-xs font-semibold tracking-widest text-gray-500 mb-1 uppercase">
                Result
              </label>
              <div className="font-mono bg-white border border-gray-200 rounded-lg px-3 py-2.5 min-h-[44px] text-lg font-semibold tracking-widest text-gray-900 break-all">
                {result || "—"}
              </div>
              {digraphDisplay && (
                <p className="text-xs text-gray-400 mt-1 font-mono">
                  Digraph pairs: {digraphDisplay}
                </p>
              )}
            </div>
          </div>

          {/* ── Right column: key square ──────────────────────────────────── */}
          <div>
            <label className="block text-xs font-semibold tracking-widest text-gray-500 mb-2 uppercase">
              Key Square
            </label>
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <KeySquare grid={grid} highlight={getHighlight()} />

              {/* Legend */}
              {activeStep !== null && (
                <div className="flex gap-4 mt-3 text-xs text-gray-500">
                  <span className="flex items-center gap-1">
                    <span className="w-3 h-3 rounded bg-blue-500 inline-block" />
                    original
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-3 h-3 rounded bg-emerald-500 inline-block" />
                    result
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Step-by-step panel ──────────────────────────────────────────── */}
        {steps.length > 0 && (
          <section className="mt-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold tracking-widest text-gray-500 uppercase">
                How it was done — click any step to highlight on the grid
              </h2>
              <div className="flex gap-3 text-xs">
                {Object.entries(RULE_LABELS).map(([k, label]) => (
                  <span key={k} className={`px-2 py-0.5 rounded font-semibold ${RULE_STYLES[k]}`}>
                    {label}
                  </span>
                ))}
              </div>
            </div>

            <StepList
              steps={steps}
              activeIndex={activeStep}
              onSelect={setActiveStep}
            />
          </section>
        )}
      </div>
    </div>
  );
}
