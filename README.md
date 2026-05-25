# 🍗 ROAST — Startup Survival Simulation

> Describe your startup idea. 6 isolated AIs simulate 3 months of real user behavior, argue about it, and a judge panel tells you if it survives — or gets roasted.

**Live demo:** [roast.up.railway.app](https://roast.up.railway.app)

---

## What it does

1. **Cast** — an LLM infers your target market and creates 4 distinct synthetic customers (name, age, personality, emoji — all AI-decided, nothing hardcoded)
2. **Simulate** — each persona runs on a different LLM model with its own isolated API key and simulates 3 months of product usage: Week 1, Month 1, Month 3 stories with satisfaction scores, best/worst moments, and willingness to pay
3. **Debate** — the most satisfied user argues with the least satisfied one, 10 rounds, with damage scores and life bars (🍗 → 🦴)
4. **Judge** — a RAG-powered investor panel reads the full transcript and scores the startup across 5 business dimensions, with prediction confidence, comparable real startups, and a survival verdict
5. **Popup** — dramatic fullscreen chicken reveal: perfectly cooked / pivot or die / 💥 BOOM ROASTED

---

## Why isolation matters

Every persona uses a **different LLM model** on a **different API key** — no shared context, no cross-contamination. The disagreement is real.

| Role | Model | Key |
|------|-------|-----|
| Persona 1 | openai/gpt-oss-20b | ROAST1 |
| Persona 2 | llama-3.1-8b-instant | ROAST2 |
| Persona 3 | meta-llama/llama-4-scout-17b-16e-instruct | ROAST3 |
| Persona 4 | qwen/qwen3-32b | ROAST4 |
| Casting | meta-llama/llama-4-scout-17b-16e-instruct | ROAST_CASTING |
| Judge (RAG) | meta-llama/llama-4-scout-17b-16e-instruct | ROAST_JUDGE |

---

## Stack

- **Backend** — Flask, Groq API, concurrent.futures for parallel LLM calls
- **Frontend** — vanilla JS, Chart.js, Bangers font
- **Charts** — line (satisfaction over time), bar (survival/retention/virality), radar (5 business criteria)
- **RAG** — rubric.md passed as context to the judge LLM
- **Deploy** — Railway

---

## Run locally

```bash
pip install flask groq python-dotenv
```

Create `.env`:

```
ROAST1=your_groq_key
ROAST2=your_groq_key
ROAST3=your_groq_key
ROAST4=your_groq_key
ROAST_CASTING=your_groq_key
ROAST_JUDGE=your_groq_key
```

Get free Groq API keys at [console.groq.com](https://console.groq.com)

```bash
python app.py
```

Visit `http://127.0.0.1:5000`

---

## Built by

Nazanin Ghelichi — solo, one night, MakersLounge Toronto Tech Week #11, Track 3: Synthetic Customers
