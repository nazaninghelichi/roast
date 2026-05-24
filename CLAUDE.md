# Roast 🍗

An AI-powered startup survival simulator. Users describe a product idea, and the app casts synthetic customer personas (via multiple isolated LLMs) who simulate 3 months of real product usage, roast each other's experiences in a debate, and get judged by a RAG-powered investor panel.

## How to run

```bash
pip install flask groq python-dotenv
python app.py
```

Visit `http://127.0.0.1:5000`

## Environment variables

Create a `.env` file with:

```
ROAST1=your_groq_key
ROAST2=your_groq_key
ROAST3=your_groq_key
ROAST4=your_groq_key
ROAST_CASTING=your_groq_key
ROAST_JUDGE=your_groq_key
```

All keys are free Groq API keys from console.groq.com.

## Models used

| Key | Model | Role |
|-----|-------|------|
| ROAST1 | llama-3.3-70b-versatile | Persona 1 |
| ROAST2 | llama-3.1-8b-instant | Persona 2 |
| ROAST3 | meta-llama/llama-4-scout-17b-16e-instruct | Persona 3 |
| ROAST4 | qwen/qwen3-32b | Persona 4 |
| ROAST_CASTING | llama-3.3-70b-versatile | Casts personas |
| ROAST_JUDGE | llama-3.3-70b-versatile | Final judgment |

## Project structure

```
roast/
  app.py             # Flask backend — all API calls and logic
  rubric.md          # Business evaluation rubric used by the judge (RAG)
  templates/
    index.html       # Frontend — all UI, charts, animations
  results/           # UUID-keyed JSON files for shareable links (gitignored)
  .env               # API keys (never commit)
```

## Flow

1. User submits a product description (min 140 chars)
2. **Casting** — one LLM infers the target audience and creates 4 distinct personas (name, role, personality, emoji) — the LLM decides everything, nothing is hardcoded
3. **Simulation** — each persona (different LLM model + key, fully isolated) simulates 3 months of product usage: Week 1, Month 1, Month 3 stories with satisfaction scores, best/worst moments, and willingness to pay
4. **Debate** — if at least one persona scored ≥50, top scorer vs bottom scorer roast each other's experience in 10 exchanges. Each hit deals 1–3 damage to a life bar (🍗 → 🦴). If all scores <50, debate is skipped.
5. **Judgment** — a separate judge LLM reads all stories + debate transcript, retrieves criteria from rubric.md, scores 5 business dimensions, gives a verdict and savage roast comment
6. **Popup** — dramatic fullscreen reveal with animated chicken: perfectly cooked (Survives) / slightly burnt (Needs work) / 💥 BOOM ROASTED (Dead on arrival)
7. **Shareable link** — result saved as `results/<uuid>.json`, accessible at `/result/<uuid>`

## Key features

- **Isolated LLMs**: each persona uses a unique API key + different model for genuinely independent responses
- **3-month simulation**: Week 1 / Month 1 / Month 3 arc — not just a score, a story
- **Life bar mechanic**: 10 lives per persona, 1–3 damage per roast exchange
- **Charts**: line chart (satisfaction over time), bar chart (survival/retention/virality), radar chart (5 business criteria)
- **Investor panel**: survival score, retention score, virality potential, 5 rubric criteria with scores and comments
- **Grounding section**: prediction confidence %, market category analogy, 2 comparable real startups with outcomes
- **Improvements**: click the verdict badge to expand actionable improvement suggestions
- **Shareable links**: UUID result storage, copy link button, `/result/<id>` renders full results on load

## Robustness

- `extract_json()`: strips `<think>` tags (qwen3), markdown fences, uses brace-depth matching, handles trailing commas
- LLM score fields default gracefully if omitted (`score`, `damage`, `new_score` all have fallbacks)
- `damage` and `new_score` are cast to `int` — LLMs sometimes return numbers as strings
- Judge uses `max_tokens=2048` to ensure full JSON including grounding fields
