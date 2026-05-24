from flask import Flask, render_template, request, jsonify
from groq import Groq
import os
import json
import re
import concurrent.futures
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


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
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print("RAW JSON FAILED:", json_str[:800])
            raise


def load_rubric():
    with open('rubric.md', 'r') as f:
        return f.read()


MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b"
]

KEYS = ["ROAST1", "ROAST2", "ROAST3", "ROAST4"]
EMOJIS = ["🧑", "👩", "🧔", "👱"]

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

    response = CASTING_CLIENT.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0
    )
    data = extract_json(response.choices[0].message.content.strip())

    return [
        {
            "name": data["personas"][i]["name"],
            "role": data["personas"][i]["role"],
            "emoji": data["personas"][i].get("emoji", "🧑"),
            "personality": data["personas"][i].get("personality", ""),
            "client": Groq(api_key=os.getenv(KEYS[i])),
            "model": MODELS[i]
        }
        for i in range(4)
    ]


def simulate_usage(persona, idea, days):
    weeks = max(1, days // 7)
    prompt = f"""You are {persona['name']}, a {persona['role']}.
Your personality: {persona.get('personality', 'honest and direct')}
You just used this product for {days} days: "{idea}"

Write your honest experience as a real human — funny, specific, a little messy.
Tell a moment or two that actually happened. Could be embarrassing, weird, surprising, or mundane.
Like a text to a friend or a brutally honest reddit review. NOT a corporate testimonial.
Be specific to YOUR life and who you are. Make it feel real.

Also give your honest satisfaction score (0-100) for each of the {weeks} weeks.
Be realistic — maybe you loved it at first then got bored, or hated it then got hooked, or just stayed consistent.

Return ONLY valid JSON:
{{
    "story": "your {days}-day experience — funny, specific, 2-4 sentences. tell an actual moment.",
    "best_moment": "one specific highlight from using it",
    "worst_moment": "one specific low point or annoyance",
    "usage_pattern": "how often you actually used it e.g. 'every morning', 'twice in week 1 then forgot'",
    "weekly_scores": [<score week 1>, <score week 2>, ...] (exactly {weeks} integers 0-100),
    "score": <your overall score 0 to 100>,
    "would_pay": "how much you'd pay to keep using it or 'nothing'"
}}"""

    response = persona["client"].chat.completions.create(
        model=persona["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0
    )
    return extract_json(response.choices[0].message.content.strip())


def debate_turn(speaker, target, idea, history, speaker_score, target_score):
    history_text = "\n".join([
        f"{h['speaker']}: {h['text']}"
        for h in history[-4:]
    ]) if history else "Battle just started."

    stance = "you loved using it" if speaker_score >= 50 else "you had a bad experience with it"
    target_stance = "loved" if target_score >= 50 else "hated"

    prompt = f"""You are {speaker['name']}, a {speaker['role']} who has actually used this product: "{idea}"
Your personality: {speaker.get('personality', 'honest and direct')}
Your experience: {stance}. {target['name']} {target_stance} it.

Recent burns:
{history_text}

Roast {target['name']}'s EXPERIENCE or TAKE on the product — not who they are as a person.
You're two real users going at it in a review thread. Attack their reasoning, their complaint, their logic.
Sound human — casual, a bit snarky, like you're texting. 1-2 sentences, open with the burn, no warm-up.
Never say "I appreciate", "fair point", or anything that sounds like a LinkedIn comment.

Score your burn:
1 = mild (meh, barely stings)
2 = solid (they felt that)
3 = CRITICAL HIT (their whole argument is cooked)

Return ONLY valid JSON:
{{
    "text": "the roast",
    "damage": <1, 2, or 3>,
    "new_score": <your updated score 0-100>
}}"""

    response = speaker["client"].chat.completions.create(
        model=speaker["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0
    )
    return extract_json(response.choices[0].message.content.strip())


def run_debate(personas, idea, reactions, total_exchanges=10):
    scores = [r['score'] for r in reactions]
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
        damage = max(1, min(3, result.get('damage', 1)))
        lives[target['name']] = max(0, lives[target['name']] - damage)
        scores[speaker_idx] = result['new_score']

        history.append({
            "round": round_num,
            "speaker": speaker['name'],
            "role": speaker['role'],
            "emoji": speaker['emoji'],
            "model": speaker['model'],
            "text": result['text'],
            "damage": damage,
            "target": target['name'],
            "score": result['new_score'],
            "side": side,
            "lives_after": dict(lives)
        })

        round_snapshots.append({
            "round": round_num,
            "exchange": exchange + 1,
            "lives": dict(lives),
            "health": round(sum(scores) / len(scores))
        })

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

    prompt = f"""You are a savage, funny, brutally honest business judge who loves roasting bad ideas.

EVALUATION RUBRIC:
{rubric}

PRODUCT IDEA: "{idea}"
TARGET AUDIENCE: "{audience}"

USER EXPERIENCE STORIES (from {days}-day simulation):
{user_stories}

DEBATE TRANSCRIPT:
{debate_text}

CUSTOMER CONSENSUS SCORE: {avg}/100

Use the rubric to score this idea. Ground your evaluation in the actual user stories above — reference specific patterns you see.
Be objective on scores. Be savage and funny in your roast_comment — specific to THIS idea, not generic startup advice.

Return ONLY valid JSON:
{{
    "problem_clarity": {{"score": <0-10>, "comment": "one sentence grounded in user stories"}},
    "market_size": {{"score": <0-10>, "comment": "one sentence"}},
    "feasibility": {{"score": <0-10>, "comment": "one sentence"}},
    "differentiation": {{"score": <0-10>, "comment": "one sentence"}},
    "revenue_potential": {{"score": <0-10>, "comment": "one sentence grounded in willingness to pay"}},
    "total": <0-50>,
    "verdict": "Fund it" or "Needs work" or "Kill it",
    "summary": "2-3 sentence overall assessment based on actual user behavior",
    "roast_comment": "savage funny roast of this specific idea, 1-2 sentences"
}}"""

    response = JUDGE_CLIENT.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return extract_json(response.choices[0].message.content.strip())


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/roast', methods=['POST'])
def roast():
    idea = request.json.get('idea', '').strip()
    audience = 'inferred from the product idea'
    days = int(request.json.get('days', 30))
    if not idea:
        return jsonify({"error": "No idea provided"}), 400

    rubric = load_rubric()
    personas = cast_personas(idea, audience)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(simulate_usage, p, idea, days) for p in personas]
        reactions = [f.result() for f in futures]

    all_hate = all(r['score'] < 50 for r in reactions)

    if all_hate:
        debate_history, final_scores, final_lives, round_snapshots = [], [r['score'] for r in reactions], {p['name']: 10 for p in personas}, []
    else:
        debate_history, final_scores, final_lives, round_snapshots = run_debate(personas, idea, reactions)

    for i, r in enumerate(reactions):
        r['_name'] = personas[i]['name']
        r['_role'] = personas[i]['role']

    judgment = judge_idea(idea, audience, debate_history, final_scores, rubric, days, reactions)

    initial_health = round(sum(r['score'] for r in reactions) / len(reactions))
    final_health = round(sum(final_scores) / len(final_scores))

    return jsonify({
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
    })


if __name__ == '__main__':
    app.run(debug=True)
