from flask import Flask, render_template, request, jsonify
from groq import Groq
import os
import json
import re
import uuid
import concurrent.futures
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

RESULTS_DIR = 'results'
os.makedirs(RESULTS_DIR, exist_ok=True)


def extract_json(text):
    original = text
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'```(?:json)?\n?', '', text)
    text = re.sub(r'```', '', text).strip()
    start = text.find('{')
    if start == -1:
        print("RAW TEXT (no JSON found):", original[:500])
        raise ValueError("No JSON found")
    depth = 0
    end = -1
    for i, c in enumerate(text[start:], start):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        print("RAW TEXT (incomplete JSON):", text[:800])
        raise ValueError("No complete JSON found")
    json_str = text[start:end]
    # Remove control characters that break JSON (LLMs sometimes embed them in strings)
    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Fix trailing commas
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Fix missing commas between fields
            json_str = re.sub(r'(["\d\]}\w])\s*\n(\s*")', r'\1,\n\2', json_str)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                print("RAW JSON FAILED:", json_str[:800])
                raise


def load_rubric():
    try:
        with open('rubric.md', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "Evaluate on: problem clarity, market size, feasibility, differentiation, revenue potential."


MODELS = [
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b"
]

KEYS = ["ROAST1", "ROAST2", "ROAST3", "ROAST4"]

CASTING_CLIENT = Groq(api_key=os.getenv("ROAST_CASTING"))
JUDGE_CLIENT = Groq(api_key=os.getenv("ROAST_JUDGE"))


def cast_personas(idea, audience):
    prompt = f"""You are casting characters for a product review panel.
Product: "{idea}"
First figure out who the realistic target audience is for this product. Then create 4 completely different real people from that audience. You decide everything:
- Their name, age, life situation
- Their personality (cynical? over-enthusiastic? pragmatic? dramatic?)
- Their relationship with technology and new products
- One emoji that captures their whole vibe
- A one-line personality note that defines HOW they talk and react

Make them feel like real distinct humans, not archetypes. Surprise us.

Return ONLY valid JSON:
{{
    "personas": [
        {{
            "name": "first name",
            "role": "age + who they are e.g. '34-year-old nurse who hates her commute'",
            "emoji": "one emoji capturing their vibe",
            "personality": "how they communicate e.g. 'blunt, uses sarcasm, low tolerance for BS'"
        }},
        {{"name": "...", "role": "...", "emoji": "...", "personality": "..."}},
        {{"name": "...", "role": "...", "emoji": "...", "personality": "..."}},
        {{"name": "...", "role": "...", "emoji": "...", "personality": "..."}}
    ]
}}"""

    fallback_models = [
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.1-8b-instant",
        "qwen/qwen3-32b"
    ]
    data = None
    for model in fallback_models:
        try:
            response = CASTING_CLIENT.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9
            )
            data = extract_json(response.choices[0].message.content.strip())
            break
        except Exception as e:
            print(f"cast_personas failed with {model}: {e}")
    if data is None:
        raise ValueError("Casting failed on all models")

    personas_data = data.get("personas", data if isinstance(data, list) else [])
    if len(personas_data) < 4:
        raise ValueError(f"Casting returned only {len(personas_data)} personas, need 4")

    return [
        {
            "name": personas_data[i].get("name", f"User {i+1}"),
            "role": personas_data[i].get("role", "product user"),
            "emoji": personas_data[i].get("emoji", "🧑"),
            "personality": personas_data[i].get("personality", "honest and direct"),
            "client": Groq(api_key=os.getenv(KEYS[i])),
            "model": MODELS[i]
        }
        for i in range(4)
    ]


def simulate_usage(persona, idea, days=None):
    prompt = f"""You are {persona['name']}, a {persona['role']}.
Your personality: {persona.get('personality', 'honest and direct')}
You used this product: "{idea}"

Simulate your realistic experience across 3 phases. Be specific, funny, human — like a reddit review or a text to a friend.
Tell actual moments. Could be embarrassing, surprising, mundane. NOT corporate speak.

Return ONLY valid JSON:
{{
    "week1": {{
        "story": "your first week — what excited you, what confused you, one specific moment",
        "score": <0-100>
    }},
    "month1": {{
        "story": "after a month — did you stick with it? what habit formed or broke? one specific moment",
        "score": <0-100>
    }},
    "month3": {{
        "story": "after 3 months — still using it? abandoned it? tell the truth with a specific detail",
        "score": <0-100>
    }},
    "best_moment": "one specific highlight",
    "worst_moment": "one specific low point",
    "would_pay": "how much you'd pay to keep using it or 'nothing'",
    "score": <overall score 0-100>
}}"""

    for attempt in range(2):
        try:
            response = persona["client"].chat.completions.create(
                model=persona["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0 if attempt == 0 else 0.5
            )
            data = extract_json(response.choices[0].message.content.strip())
            if 'score' not in data:
                sub = [data.get('week1', {}).get('score', 50),
                       data.get('month1', {}).get('score', 50),
                       data.get('month3', {}).get('score', 50)]
                data['score'] = round(sum(sub) / len(sub))
            return data
        except Exception as e:
            print(f"simulate_usage attempt {attempt+1} failed for {persona['name']}: {e}")
            if attempt == 1:
                return {"week1": {"story": "Had a mixed experience.", "score": 50},
                        "month1": {"story": "Used it occasionally.", "score": 50},
                        "month3": {"story": "Still around but not a daily habit.", "score": 50},
                        "best_moment": "When it actually worked well",
                        "worst_moment": "When it didn't",
                        "would_pay": "$5/month",
                        "score": 50}


def debate_turn(speaker, target, idea, history, speaker_score, target_score):
    history_text = "\n".join([
        f"{h['speaker']}: {h['text']}"
        for h in history
    ]) if history else "The argument just started."

    stance = "you loved using it" if speaker_score >= 50 else "you had a bad experience with it"
    target_stance = "loved" if target_score >= 50 else "hated"

    exchanges_so_far = len(history)
    concede_instruction = (
        "You've been going back and forth for a while. If they have thoroughly dismantled every single point you've made across multiple rounds and you genuinely have nothing left, you may concede — set \"concede\": true. This should be rare and hard-earned."
        if exchanges_so_far >= 4 else
        "Do NOT concede. You just started — hold your ground no matter what."
    )

    prompt = f"""You are {speaker['name']}, a {speaker['role']} who actually used this product: "{idea}"
Your personality: {speaker.get('personality', 'honest and direct')}
Your experience: {stance}. {target['name']} {target_stance} it.

This is a live heated argument thread. You are stubborn, passionate, and you believe you are right. Read every message carefully. Respond specifically to what {target['name']} just said — attack the flaw in their logic, call out what they're ignoring, use your own experience as proof.

Full argument so far:
{history_text}

Now fire back at {target['name']}'s last message. Be specific. Be sharp. 2-3 sentences — enough to actually land a real argument, not just a one-liner. Bring receipts from your experience. Casual tone, like a heated review thread.
Never say "I appreciate", "fair point", "that's a good point", or anything diplomatic.

{concede_instruction}

Rate your hit:
1 = mild  2 = solid  3 = CRITICAL HIT (their entire argument is cooked)

Return ONLY valid JSON:
{{
    "text": "your response",
    "damage": <1, 2, or 3>,
    "new_score": <your updated satisfaction score 0-100>,
    "concede": <true only if exchanges >= 4 AND they've proven every point, otherwise ALWAYS false>
}}"""

    for attempt in range(2):
        try:
            response = speaker["client"].chat.completions.create(
                model=speaker["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0 if attempt == 0 else 0.5
            )
            return extract_json(response.choices[0].message.content.strip())
        except Exception as e:
            print(f"debate_turn attempt {attempt+1} failed for {speaker['name']}: {e}")
            if attempt == 1:
                return {"text": "...", "damage": 1, "new_score": speaker_score, "concede": False}


def run_debate(personas, idea, reactions, total_exchanges=10):
    scores = [int(r.get('score', 50)) for r in reactions]
    lives = {p['name']: 10 for p in personas}
    history = []
    round_snapshots = []
    turn = 0  # 0 = supporter attacks, 1 = skeptic attacks, alternates

    for exchange in range(total_exchanges):
        alive = [i for i, p in enumerate(personas) if lives[p['name']] > 0]
        if len(alive) < 2:
            break

        sorted_by_score = sorted(alive, key=lambda i: -scores[i])
        supporters = sorted_by_score[:len(sorted_by_score)//2 + 1]
        skeptics = sorted_by_score[len(sorted_by_score)//2:]

        if supporters[0] == skeptics[0] or not supporters or not skeptics:
            break

        round_num = exchange // 2 + 1

        if turn == 0:
            speaker_idx, target_idx = supporters[0], skeptics[0]
            side = "support"
        else:
            speaker_idx, target_idx = skeptics[0], supporters[0]
            side = "skeptic"

        speaker = personas[speaker_idx]
        target = personas[target_idx]

        result = debate_turn(speaker, target, idea, history, scores[speaker_idx], scores[target_idx])
        damage = max(1, min(3, int(result.get('damage', 1))))
        conceded = bool(result.get('concede', False))
        lives[target['name']] = max(0, lives[target['name']] - damage)
        scores[speaker_idx] = int(result.get('new_score', scores[speaker_idx]))

        history.append({
            "round": round_num,
            "speaker": speaker['name'],
            "role": speaker['role'],
            "emoji": speaker['emoji'],
            "model": speaker['model'],
            "text": result['text'],
            "damage": damage,
            "target": target['name'],
            "score": result.get('new_score', scores[speaker_idx]),
            "side": side,
            "lives_after": dict(lives),
            "conceded": conceded
        })

        round_snapshots.append({
            "round": round_num,
            "exchange": exchange + 1,
            "lives": dict(lives),
            "health": round(sum(scores) / len(scores))
        })

        # End early if speaker conceded — but only after at least 4 exchanges
        if conceded and exchange >= 4:
            break

        # End early if scores have converged — they've met in the middle (after min 4 exchanges)
        if exchange >= 3 and abs(scores[supporters[0]] - scores[skeptics[0]]) <= 12:
            break

        turn = 1 - turn

    return history, scores, lives, round_snapshots


def judge_idea(idea, audience, history, final_scores, rubric, days, reactions):
    debate_text = "\n".join([
        f"Round {h['round']} - {h['speaker']} ({h['role']}, score {h['score']}): {h['text']}"
        for h in history
    ])
    avg = round(sum(final_scores) / len(final_scores))
    user_stories = "\n\n".join([
        f"{r.get('_name','User')} ({r.get('_role','')}):\n"
        f"Story: {r.get('story','')}\n"
        f"Best moment: {r.get('best_moment','')}\n"
        f"Worst moment: {r.get('worst_moment','')}\n"
        f"Usage: {r.get('usage_pattern','')}\n"
        f"Score: {r.get('score',0)}/100 | Would pay: {r.get('would_pay','?')}"
        for r in reactions
    ])

    prompt = f"""You are a panel of savage, brutally honest investors evaluating a startup.

EVALUATION RUBRIC:
{rubric}

STARTUP IDEA: "{idea}"

USER SIMULATION DATA (3-month experience from real synthetic customers):
{user_stories}

CUSTOMER DEBATE TRANSCRIPT:
{debate_text}

CUSTOMER CONSENSUS SCORE: {avg}/100

You've seen the user data. Now evaluate this startup like a VC who has heard 1000 pitches.
Be grounded in the actual user stories — reference specific patterns you see.
Be objective on scores. Be savage and specific in your roast_comment.

Return ONLY valid JSON:
{{
    "survival_score": <0-100, would this startup survive 1 year>,
    "retention_score": <0-100, based on the 3-month user data>,
    "virality_potential": <0-100, would users tell others>,
    "problem_clarity": {{"score": <0-10>, "comment": "one sentence"}},
    "market_size": {{"score": <0-10>, "comment": "one sentence"}},
    "feasibility": {{"score": <0-10>, "comment": "one sentence"}},
    "differentiation": {{"score": <0-10>, "comment": "one sentence"}},
    "revenue_potential": {{"score": <0-10>, "comment": "one sentence grounded in willingness to pay"}},
    "total": <0-50>,
    "biggest_risk": "the one thing most likely to kill this startup",
    "strongest_advantage": "the one real thing going for it",
    "verdict": "Survives" or "Needs work" or "Dead on arrival",
    "summary": "2-3 sentence investor-style assessment",
    "roast_comment": "savage funny roast specific to this startup, 1-2 sentences",
    "prediction_confidence": <0-100, how confident you are in this verdict given data quality and market clarity>,
    "market_analogy": "one sentence: what existing market this maps to and its dynamics",
    "comparable_startups": [
        {{"name": "real startup name", "outcome": "what happened and why relevant"}},
        {{"name": "real startup name", "outcome": "what happened and why relevant"}}
    ],
    "improvements": [
        "specific actionable improvement #1",
        "specific actionable improvement #2",
        "specific actionable improvement #3"
    ]
}}"""

    judge_models = ["meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant"]
    for model in judge_models:
        try:
            response = JUDGE_CLIENT.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048
            )
            return extract_json(response.choices[0].message.content.strip())
        except Exception as e:
            print(f"judge_idea failed with {model}: {e}")
    raise ValueError("Judge failed on all models")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/slides')
def slides():
    return render_template('slides.html')


@app.route('/roast', methods=['POST'])
def roast():
    try:
        idea = request.json.get('idea', '').strip()
    except Exception:
        return jsonify({"error": "Bad request"}), 400
    audience = 'inferred from the product idea'
    days = 90
    if not idea:
        return jsonify({"error": "No idea provided"}), 400

    try:
        rubric = load_rubric()
        personas = cast_personas(idea, audience)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(simulate_usage, p, idea) for p in personas]
            reactions = [f.result() for f in futures]

        all_hate = all(r.get('score', 50) < 50 for r in reactions)

        if all_hate:
            debate_history, final_scores, final_lives, round_snapshots = [], [r.get('score', 50) for r in reactions], {p['name']: 10 for p in personas}, []
        else:
            debate_history, final_scores, final_lives, round_snapshots = run_debate(personas, idea, reactions)

        for i, r in enumerate(reactions):
            r['_name'] = personas[i]['name']
            r['_role'] = personas[i]['role']

        judgment = judge_idea(idea, audience, debate_history, final_scores, rubric, days, reactions)

        initial_health = round(sum(r.get('score', 50) for r in reactions) / len(reactions))
        final_health = round(sum(final_scores) / len(final_scores))

        result_id = str(uuid.uuid4())[:8]
        result = {
            "id": result_id,
            "idea": idea,
            "personas": [
                {
                    "name": personas[i]['name'],
                    "role": personas[i]['role'],
                    "emoji": personas[i]['emoji'],
                    "personality": personas[i].get('personality', ''),
                    "model": personas[i]['model'],
                    "reaction": reactions[i],
                    "final_score": final_scores[i],
                    "final_lives": final_lives[personas[i]['name']]
                }
                for i in range(len(personas))
            ],
            "days": days,
            "debate": debate_history,
            "round_snapshots": round_snapshots,
            "all_hate": all_hate,
            "initial_health": initial_health,
            "final_health": final_health,
            "judgment": judgment
        }

        with open(f'{RESULTS_DIR}/{result_id}.json', 'w') as f:
            json.dump(result, f)

        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/result/<result_id>')
def view_result(result_id):
    path = f'{RESULTS_DIR}/{result_id}.json'
    if not os.path.exists(path):
        return "Result not found", 404
    with open(path) as f:
        data = json.load(f)
    return render_template('index.html', prefill=data)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
