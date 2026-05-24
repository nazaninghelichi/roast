# Roast 🍗

An AI-powered product feedback simulator. Users describe a product idea, and the app casts synthetic customer personas (via multiple LLMs) who simulate using it over X days, roast each other's opinions in a debate, and get judged by a RAG-powered head chef.

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
  app.py          # Flask backend — all API calls and logic
  rubric.md       # Business evaluation rubric used by the judge (RAG)
  templates/
    index.html    # Frontend — all UI, chart, animations
  .env            # API keys (never commit)
```

## Flow

1. User submits a product description (min 140 chars) + number of days to simulate
2. **Casting** — one LLM infers the target audience and creates 4 distinct personas (name, role, personality, emoji)
3. **Simulation** — each persona (different LLM model + key) simulates X days of product usage and returns a story, weekly satisfaction scores, best/worst moments
4. **Debate** — top scorer vs bottom scorer roast each other's experience in 10 exchanges. Each hit deals 1-3 damage to a life bar (🍗 → 🦴)
5. **Judgment** — a separate judge LLM reads all stories + debate transcript, retrieves criteria from rubric.md, scores 5 business dimensions, gives a verdict and savage roast comment
6. **Popup** — dramatic fullscreen reveal with animated chicken: perfectly cooked / slightly burnt / 💥 BOOM ROASTED
