"""Rule-based answers about Mayank's career, projects, services and research, from profile.json.

Contract: answer(text, memory) -> str | None. None means "not about Mayank, let PyBot's other
modules take it". Replies are Markdown. Two memory keys are read and written:

  memory["portfolio_agent"]        set by the host app: welcome | career | project | client | research.
                                   When set, the chat is the portfolio, so "you"/"he" mean Mayank.
  memory["portfolio_last"]         the last topic answered, so "tell me more" goes deeper.
  memory["portfolio_suggestions"]  up to three follow-up questions for the host to show as chips.
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.environ.get("PORTFOLIO_PROFILE") or os.path.join(_HERE, "profile.json")

with open(PROFILE_PATH, encoding="utf-8") as _fh:
    P = json.load(_fh)

NAME = P["name"]
FIRST = NAME.split()[0]
EMAIL = P["contact"]["email"]

AGENTS = {
    "welcome": ("Ava", "Concierge", "Town Hall"),
    "career": ("Theo", "Career Advisor", "Career HQ"),
    "project": ("Nova", "Project Lead", "Engineering Lab"),
    "client": ("Max", "Business Advisor", "Services Studio"),
    "research": ("Iris", "Research Analyst", "Research Tower"),
}

SUGGEST = {
    "welcome": ["Who is Mayank?", "What is he working on now?", "Which agent should I talk to?"],
    "career": ["Summarise his experience", "What are his strongest skills?", "Paste a job description for a fit check"],
    "project": ["List his projects", "How does Netskope Cloud Exchange scale?", "Tell me about the AI governance gateway"],
    "client": ["What services does he offer?", "How does an engagement work?", "How do I get a quote?"],
    "research": ["What are his research interests?", "Rule-based bots vs LLMs?", "What is AI governance?"],
}

# ---------------------------------------------------------------- text helpers

_WORD = re.compile(r"[a-z0-9+#.]+")


def _norm(text):
    return " ".join(_WORD.findall(text.lower().replace("’", "'")))


def _has(text, *patterns):
    return any(re.search(p, text) for p in patterns)


def _bullets(items, limit=None):
    items = list(items)[:limit] if limit else list(items)
    return "\n".join(f"- {i}" for i in items)


# Words that say the line is about Mayank. In portfolio mode, "you", "he" and friends count too.
_NAMED = r"\b(mayank|ranghadiya|mayank's)\b"
_PRONOUN = r"\b(he|him|his|you|your|yours|you're|ur|u|candidate|developer|engineer|profile|cv|resume|portfolio)\b"

# ---------------------------------------------------------------- skills lexicon (for skill checks and job fit)

# canonical skill -> aliases that may appear in a question or a job description
LEXICON = {
    "Python": ["python", "py"], "JavaScript": ["javascript", "js", "es6"], "TypeScript": ["typescript", "ts"],
    "Bash": ["bash", "shell", "scripting"], "FastAPI": ["fastapi"], "Django": ["django", "drf"], "Flask": ["flask"],
    "Celery": ["celery"], "asyncio": ["asyncio", "async", "asynchronous"], "gRPC": ["grpc", "protobuf"],
    "REST APIs": ["rest", "restful", "api", "apis"], "WebSockets": ["websocket", "websockets"],
    "Microservices": ["microservice", "microservices"], "AI Agents": ["agent", "agents", "agentic"],
    "RAG": ["rag", "retrieval"], "LangChain": ["langchain"], "MCP": ["mcp", "model context protocol"],
    "OpenAI": ["openai", "gpt"], "AWS Bedrock": ["bedrock"], "Vertex AI": ["vertex"], "Groq": ["groq"],
    "TensorFlow": ["tensorflow"], "Prompt Engineering": ["prompt", "prompting"],
    "LLMs": ["llm", "llms", "genai", "generative ai", "ai", "ml", "machine learning"],
    "PostgreSQL": ["postgres", "postgresql", "psql"], "MongoDB": ["mongo", "mongodb", "nosql"],
    "MySQL": ["mysql", "sql", "mssql", "oracle"], "Redis": ["redis"], "RabbitMQ": ["rabbitmq", "amqp", "message queue", "queues"],
    "Docker": ["docker", "container", "containers"], "Kubernetes": ["kubernetes", "k8s", "helm"],
    "AWS": ["aws", "amazon web services"], "GCP": ["gcp", "google cloud"], "Azure": ["azure"],
    "CI/CD": ["ci", "cd", "ci/cd", "cicd", "pipelines", "github actions", "jenkins"],
    "Observability": ["observability", "monitoring", "logging", "tracing", "prometheus", "grafana"],
    "React": ["react", "reactjs", "react.js"], "WebRTC": ["webrtc"], "Node.js": ["node", "nodejs", "node.js"],
    "System Design": ["system design", "architecture", "architect", "scalable", "scalability", "distributed"],
    "Mentoring": ["mentor", "mentoring", "mentorship", "coaching"],
    "Leadership": ["lead", "leadership", "manage", "management", "head of", "team lead"],
    "Agile": ["agile", "scrum", "kanban"], "Testing (pytest)": ["pytest", "testing", "unit test", "tdd"],
    "Selenium": ["selenium"], "Whisper": ["whisper"], "Streamlit": ["streamlit"],
    "Three.js": ["three.js", "threejs", "webgl"],
}
# Known technologies Mayank does NOT list: they count as gaps in a job description.
NOT_LISTED = {
    "Java": ["java", "spring", "spring boot"], "Go": ["golang", "go lang"], "Rust": ["rust"],
    "C++": ["c++", "cpp"], "C#/.NET": ["c#", ".net", "dotnet"], "Ruby": ["ruby", "rails"], "PHP": ["php", "laravel"],
    "Kafka": ["kafka"], "Spark": ["spark", "pyspark"], "Airflow": ["airflow"], "Terraform": ["terraform"],
    "Angular": ["angular"], "Vue": ["vue", "vuejs"], "Swift/iOS": ["swift", "ios"], "Kotlin/Android": ["kotlin", "android"],
    "PyTorch": ["pytorch"], "Snowflake": ["snowflake"], "Elasticsearch": ["elasticsearch", "elastic"],
}


def _alias_re(alias):
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")


_LEX_RE = {k: [_alias_re(a) for a in v] for k, v in LEXICON.items()}
_GAP_RE = {k: [_alias_re(a) for a in v] for k, v in NOT_LISTED.items()}


def _find_terms(text, table):
    low = text.lower()
    return [k for k, regs in table.items() if any(r.search(low) for r in regs)]


def _evidence(skill, strong_only=False):
    """The strongest CV lines that mention a skill (or its aliases): achievements first, then usage."""
    regs = _LEX_RE.get(skill, [_alias_re(skill.lower())])
    strong, weak = [], []
    for job in P["experience"]:
        lines = [h for h in job["highlights"] if any(r.search(h.lower()) for r in regs)]
        strong += [f"{h} *({job['company']})*" for h in lines]
        if not lines and any(r.search(" ".join(job["tech"]).lower()) for r in regs):
            weak.append(f"Used at {job['company']} ({job['period']}).")
    for proj in P["projects"]:
        if any(r.search(" ".join(proj["tech"]).lower() + " " + proj["summary"].lower()) for r in regs):
            strong.append(f"Project **{proj['name']}**: {proj['summary']}")
    return strong if strong_only else strong + weak


# ---------------------------------------------------------------- topics

def _intro(agent):
    who, role, building = AGENTS.get(agent, AGENTS["welcome"])
    return who, role, building


def about():
    m = P["metrics"]
    return (
        f"**{NAME}** is a {P['title']} with **{P['years_experience']} years** of experience, "
        f"based in {P['location']}.\n\n{P['headline']}\n\n"
        f"Highlights: **{m[0]['value']}** {m[0]['label']}, **{m[1]['value']}** {m[1]['label']}, "
        f"**{m[2]['value']}** {m[2]['label']}. He is currently Head of Engineering at **CognitivTrust**, "
        "building an AI governance platform."
    )


def current_role():
    job = P["experience"][0]
    return f"**{job['role']}** at **{job['company']}** ({job['period']}).\n\n{job['summary']}\n\n" + _bullets(job["highlights"], 4)


def experience_overview():
    lines = [f"**{j['role']}**, {j['company']} · {j['period']}: {j['summary']}" for j in P["experience"]]
    return f"{FIRST} has **{P['years_experience']} years** across startups, enterprise and freelance work:\n\n" + _bullets(lines)


def job_detail(job, deep=False):
    if deep:
        rest = job["highlights"][4:] or job["highlights"]
        return f"More from **{job['company']}**:\n\n" + _bullets(rest) + f"\n\nStack: {', '.join(job['tech'])}"
    body = _bullets(job["highlights"][:4])
    more = "" if len(job["highlights"]) <= 4 else "\n\nAsk *tell me more* for the rest."
    return (f"**{job['role']}** at **{job['company']}** ({job['period']})\n\n{job['summary']}\n\n{body}\n\n"
            f"Stack: {', '.join(job['tech'])}{more}")


def skills_overview():
    return f"{FIRST}'s skills, grouped:\n\n" + _bullets(f"**{g}**: {', '.join(s)}" for g, s in P["skills"].items())


def skill_check(skill):
    ev = _evidence(skill)
    if ev:
        return f"Yes: **{skill}** is part of {FIRST}'s toolkit.\n\n" + _bullets(ev, 3)
    if any(skill in group for group in P["skills"].values()):
        return f"Yes: **{skill}** is on {FIRST}'s skills list. For specifics, email [{EMAIL}](mailto:{EMAIL})."
    return None


def skill_gap(skill):
    return (f"**{skill}** isn't on {FIRST}'s CV. His core is Python, distributed systems (Celery, RabbitMQ, Redis), "
            f"AI agents/RAG and cloud (AWS, GCP, Azure). Ask him directly at [{EMAIL}](mailto:{EMAIL}).")


def projects_overview():
    return "Projects and systems:\n\n" + _bullets(f"**{p['name']}**: {p['summary']}" for p in P["projects"])


def project_detail(proj):
    link = f"\n\nCode: {proj['github']}" if proj.get("github") else ""
    return f"**{proj['name']}**\n\n{proj['summary']}\n\n{proj['details']}\n\nStack: {', '.join(proj['tech'])}{link}"


def metrics():
    return f"Impact in numbers:\n\n" + _bullets(f"**{m['value']}** {m['label']}" for m in P["metrics"])


def education():
    return "Education:\n\n" + _bullets(f"**{e['degree']}**, {e['school']} ({e['period']})" for e in P["education"])


def certifications():
    return "Certifications & recognition:\n\n" + _bullets(P["certifications"])


def contact():
    c = P["contact"]
    return (f"Reach {FIRST} at:\n\n- Email: [{c['email']}](mailto:{c['email']})\n- LinkedIn: {c['linkedin']}\n"
            f"- GitHub: {c['github']}\n\nThe Contact page has the same links.")


def services():
    return (f"{FIRST} takes on focused engagements in:\n\n" + _bullets(f"**{s['name']}**: {s['description']}" for s in P["services"])
            + f"\n\nDescribe your problem and I'll sketch a plan, or email [{EMAIL}](mailto:{EMAIL}).")


def process():
    return ("A typical engagement:\n\n1. **Discovery**: goals, constraints, current system (a call or a short doc).\n"
            "2. **Architecture**: a written design with trade-offs, milestones and risks.\n"
            "3. **Build**: iterative delivery with demos, tests and observability baked in.\n"
            "4. **Handover**: docs, runbooks and knowledge transfer to your team.\n\n"
            f"Pricing depends on scope, so for a quote email [{EMAIL}](mailto:{EMAIL}).")


def pricing():
    return (f"Rates depend on scope and duration, and I don't quote them here. Send a short brief to "
            f"[{EMAIL}](mailto:{EMAIL}) and {FIRST} will come back with an estimate.")


def research():
    return f"{FIRST}'s research interests:\n\n" + _bullets(P["research_interests"]) + "\n\nPick one and I'll go deeper."


# General framing is labelled as such; every claim about Mayank comes from profile.json.
TOPIC_NOTES = {
    "governance": ("**AI governance** for engineering teams means visibility and control over what AI coding tools send "
                   "and generate. At CognitivTrust, Mayank is building a zero-configuration gateway that intercepts and "
                   "routes IDE-generated AI requests for real-time policy enforcement, plus a context layer that feeds "
                   "organizational documents (policies, release rules) into AI interactions."),
    "rag": ("**RAG / context engineering** means retrieving the right knowledge and putting it in front of a model when "
            "it answers. Mayank has built it three ways: CognitivTrust's context layer over org policies and release rules, "
            "**Voice RAG** (Whisper + LangChain + Streamlit) and **Chat with your Data** (Node.js, React, Groq)."),
    "agents": ("**Agents & MCP**: agents are LLM loops that call tools, and the Model Context Protocol standardizes how "
               "tools and context reach them. Agents, RAG, LangChain and MCP are on Mayank's skills list, and his current "
               "work governs AI-assisted development at the gateway level."),
    "distributed": ("**High-throughput task processing**: at Crest Data, Mayank built and scaled Python distributed systems "
                    "on Celery, RabbitMQ and Redis processing **300K+ events/min** for **1M+ users** and **7K+ jobs/day**, "
                    "improved performance 25% across clouds and on-prem, and cut processing time 30% through regular "
                    "benchmarking. Ask Nova in the Engineering Lab about Netskope Cloud Exchange for more."),
    "pybot": ("**Rule-based vs LLM chatbots**: this town runs on PyBot, a chatbot written in plain Python (regex, if-else "
              "and lookup tables, no model) that Mayank forked and taught his CV. The trade-off: rules are free, "
              "deterministic and can't invent facts about him, but they only cover what has been written down. For "
              "exact career facts that's the right trade, and PyBot's general rules still handle small talk."),
}


def why_hire():
    return ("Why talk to Mayank:\n\n"
            "- **Proven at scale**: systems at 300K+ events/min, 1M+ users, 7K+ jobs/day.\n"
            "- **0→1 owner**: led 7+ modules from scratch; now founding Head of Engineering at an AI startup.\n"
            "- **AI + platform depth**: production AI governance gateway, RAG context layer, agents and MCP.\n"
            "- **Multiplier**: mentored 4 engineers, set up engineering workflows and release processes.\n\n"
            "Paste a job description and Theo in Career HQ will check the fit.")


def leadership():
    return ("Leadership and ownership:\n\n"
            "- Head of Engineering and founding engineer at CognitivTrust, setting architecture and release processes.\n"
            "- Led 7+ modules 0→1 at Crest Data; mentored 4 engineers (intern to senior) in a team of 7–10.\n"
            "- Key technical contact for stakeholders, turning business requirements into system designs.\n"
            "- Consulted freelance clients on backend architecture and API design.")


def help_text(agent):
    who, role, building = _intro(agent)
    focus = {
        "welcome": "a quick overview of Mayank and which agent to visit",
        "career": "experience, skills, education, and a job-fit check (paste a job description)",
        "project": "his projects and systems: architecture, scale and stack",
        "client": "services, how an engagement works, and how to get a quote",
        "research": "AI governance, RAG, agents & MCP, distributed processing, rule-based bots",
    }[agent if agent in AGENTS else "welcome"]
    return f"I'm **{who}**, the {role} in the {building}. I can help with {focus}."


def greeting(agent):
    who, role, building = _intro(agent)
    return f"Hi! I'm **{who}**, the {role} here in the {building}. " + help_text(agent).split(". ", 1)[1]


def directory():
    return ("The town's agents:\n\n- **Ava** (Town Hall): overview and directions\n"
            "- **Theo** (Career HQ): experience, skills, job-fit checks\n- **Nova** (Engineering Lab): projects and architecture\n"
            "- **Max** (Services Studio): services and engagements\n- **Iris** (Research Tower): AI governance, RAG, agents\n\n"
            "Click a building to visit, or just ask me.")


# ---------------------------------------------------------------- job fit

_JD_HINT = r"\b(job description|jd|requirements?|responsibilities|qualifications|we are looking|you will|must have|nice to have|role:|about the role)\b"


def looks_like_jd(text, agent):
    words = len(text.split())
    if words >= 60:
        return True
    return words >= 15 and (bool(re.search(_JD_HINT, text.lower())) or agent == "career" and "fit" in text.lower())


def job_fit(text):
    matched = _find_terms(text, _LEX_RE)
    gaps = _find_terms(text, _GAP_RE)
    if "Go" not in gaps and re.search(r"(?<![A-Za-z])Go(?![A-Za-z-])", text):  # "Go", not "go"
        gaps.append("Go")
    low = text.lower()
    years = [int(y) for y in re.findall(r"(\d{1,2})\s*\+?\s*(?:-\s*\d+\s*)?years?", low)]
    need = max(years) if years else None
    seniority = re.search(r"\b(staff|principal|lead|head of|senior|sr\.?|architect|founding)\b", low)

    total = len(matched) + len(gaps)
    score = len(matched) / total if total else 0.5
    if need is not None and need > 8:
        score -= 0.15
    verdict = "Strong fit" if score >= 0.7 else "Good fit" if score >= 0.45 else "Partial fit"

    out = [f"### {verdict}", ""]
    if matched:
        out.append(f"**Matches ({len(matched)})**: " + ", ".join(matched))
        out.append("")
        ev = []
        for s in matched:
            for line in _evidence(s, strong_only=True)[:1]:
                if line not in ev:
                    ev.append(line)
        if ev:
            out += ["**Evidence from the CV**", _bullets(ev, 5), ""]
    if need is not None:
        ok = "meets" if need <= 7 else "is close to" if need <= 8 else "is below"
        out += [f"**Experience**: the role asks for {need}+ years; Mayank has 7+, which {ok} it.", ""]
    if seniority:
        out.append(f"**Seniority**: the role is {seniority.group(1)}-level; Mayank is Head of Engineering now, "
                   "has led 7+ modules 0→1 and mentored 4 engineers.")
        out.append("")
    if gaps:
        out += [f"**Gaps to discuss**: {', '.join(gaps)}. These aren't on the CV; his Python and distributed-systems "
                    "depth usually transfers quickly."]
    if not matched and not gaps:
        out.append("I couldn't spot specific technologies in that text. Paste the full job description and I'll compare it line by line.")
    out += ["", "**Talking points**",
            "- Scaled pipelines to 300K+ events/min and 7K+ jobs/day (Celery, RabbitMQ, Redis).",
            "- Founding Head of Engineering building an AI governance gateway and RAG context layer.",
            "- Cut processing time 30% through systematic benchmarking.",
            "", f"To take it further: [{EMAIL}](mailto:{EMAIL})"]
    return "\n".join(out)


# ---------------------------------------------------------------- router

def _match_job(t):
    keys = {
        "CognitivTrust": r"cognitiv|cognitive trust|current (company|job|employer)",
        "Crest Data": r"crest|netskope|cloud exchange",
        "Sourcewiz": r"sourcewiz|source wiz|zara|jaipur rugs|surya",
        "HHAeXchange": r"hhaexchange|hha|home care|patient module",
        "Self-Employed": r"freelanc|self employed|self-employed|consult(ing|ancy) work",
    }
    for job in P["experience"]:
        if re.search(keys.get(job["company"], r"$^"), t):
            return job
    return None


def _match_project(t):
    keys = {
        "portfolio-agents": r"this (site|portfolio|town|website)|agent town|portfolio (site|project|app)",
        "ai-governance-gateway": r"gateway|governance (platform|gateway)",
        "netskope-ce": r"netskope|cloud exchange",
        "voice-rag": r"voice",
        "db-ai-chat": r"chat with (your )?data|database chat|db ai|talk to (your )?database",
        "whatsapp-integration": r"whatsapp",
    }
    for proj in P["projects"]:
        if re.search(keys.get(proj["id"], r"$^"), t):
            return proj
    return None


def _skill_asked(t):
    m = re.search(r"\b(know|knows|use|uses|used|experience (with|in)|worked (with|on)|familiar with|good at|"
                  r"proficient in|skilled in|expert in|work with|done any|built with|tried)\b(.*)", t)
    return m.group(m.lastindex) if m else None


def _route(text, agent, last):
    t = _norm(text)
    raw = text.strip()

    # Conversation glue
    if re.fullmatch(r"(hi|hello|hey|hiya|good (morning|afternoon|evening)|yo|namaste)( there| [a-z]+)?", t):
        return "greeting", greeting(agent)
    if _has(t, r"^(help|what can you (do|tell)|what do you do|who are you|what should i ask)"):
        return "help", help_text(agent)
    if _has(t, r"which agent|who (else|should i talk)|other agents|the agents|directory|where (should|do) i go"):
        return "directory", directory()
    if last and _has(t, r"^(tell me more|more( details)?|go on|elaborate|details|expand|keep going|and)\b"):
        kind, _, key = last.partition(":")
        if kind == "job":
            job = next((j for j in P["experience"] if j["company"] == key), None)
            if job:
                return last, job_detail(job, deep=True)
        if kind == "project":
            proj = next((p for p in P["projects"] if p["id"] == key), None)
            if proj:
                return last, project_detail(proj)
        if kind in ("experience", "about"):
            return "job:" + P["experience"][0]["company"], job_detail(P["experience"][0], deep=True)
        if kind == "projects":
            return "project:" + P["projects"][1]["id"], project_detail(P["projects"][1])
        if kind == "skills":
            return "skills", leadership()

    # Job description pasted
    if looks_like_jd(raw, agent):
        return "fit", job_fit(raw)

    # Specific project (names are more specific than employers), then employer
    proj = _match_project(t)
    if proj:
        return "project:" + proj["id"], project_detail(proj)
    job = _match_job(t)
    if job:
        return "job:" + job["company"], job_detail(job)

    # A specific technology ("does he know X", "has he worked with Y")
    asked = _skill_asked(t)
    if asked is not None:
        hits, gaps = _find_terms(asked, _LEX_RE), _find_terms(asked, _GAP_RE)
        hits = [h for h in hits if h not in ("Leadership", "REST APIs")] or hits
        if hits and skill_check(hits[0]):
            return "skill:" + hits[0], skill_check(hits[0])
        if gaps:
            return "skill:" + gaps[0], skill_gap(gaps[0])

    # Research topics
    if _has(t, r"governance|policy enforcement"):
        return "research:governance", TOPIC_NOTES["governance"]
    if _has(t, r"\brag\b|retrieval|context (layer|engineering)|embedding|vector"):
        return "research:rag", TOPIC_NOTES["rag"]
    if _has(t, r"\bmcp\b|model context protocol|agentic|ai agents?"):
        return "research:agents", TOPIC_NOTES["agents"]
    if _has(t, r"pybot|rule.based|rules vs|vs (an )?llm|without (an )?llm|no llm|how (does|do) (this|you) work|are you (an? )?(ai|llm|bot|gpt)"):
        return "research:pybot", TOPIC_NOTES["pybot"]
    if _has(t, r"celery|rabbitmq|throughput|events per minute|high.throughput|task (queue|processing)|distributed system"):
        return "research:distributed", TOPIC_NOTES["distributed"]
    if _has(t, r"research|interests?|exploring|curious about|thought leadership|trends"):
        return "research", research()

    # Hiring and services
    if _has(t, r"why (should|would) (i|we) hire|why hire|strengths?|stand out|unique|good fit|what makes"):
        return "why", why_hire()
    if _has(t, r"\b(price|pricing|rate|rates|cost|charge|budget|hourly|fees?)\b"):
        return "pricing", pricing()
    if _has(t, r"process|how (does|do) (an |the )?(engagement|it|working|this) work|engagement|onboard"):
        return "process", process()
    if _has(t, r"services?|offer|offerings|hire (him|you)|freelance|consult|contract work|help (me|us|my|our)|build (me|us|for)"):
        return "services", services()
    if _has(t, r"contact|reach|email|e mail|linkedin|github|get in touch|connect|resume|cv\b|phone|call"):
        return "contact", contact()

    # Career
    if _has(t, r"lead(er|ership)?\b|mentor|manage(r|ment)?|team size|head of"):
        return "leadership", leadership()
    if _has(t, r"educat|degree|college|university|studied|study|school|graduat|b\.?tech|cgpa"):
        return "education", education()
    if _has(t, r"certif|award|recogni|achievement|accomplish"):
        return "certifications", certifications()
    if _has(t, r"metric|numbers|impact|scale|biggest|results"):
        return "metrics", metrics()
    if _has(t, r"languages? (does|do) (he|you) speak|speak|spoken"):
        return "languages", f"{FIRST} speaks {', '.join(P['languages'])}."
    if _has(t, r"where (is|are|does) .*(based|live|located|from)|location|relocat|remote|time ?zone"):
        return "location", (f"{FIRST} is based in {P['location']}. For remote/relocation and availability, "
                            f"email [{EMAIL}](mailto:{EMAIL}).")
    if _has(t, r"availab|notice period|open to (work|opportunit)|looking for (a )?(job|role)|salary|ctc|compensation"):
        return "availability", (f"Availability, notice period and compensation aren't something I can answer; "
                                f"{FIRST} handles those directly at [{EMAIL}](mailto:{EMAIL}).")
    if _has(t, r"(how many|how much|years of) (years|experience)|how (long|experienced|senior)|seniority|years"):
        return "years", (f"**{P['years_experience']} years** of professional engineering (since 2020, freelance first), "
                         f"now at Head of Engineering level.\n\n" + metrics())
    if _has(t, r"(current|now|today|present|latest)\b.*(job|role|work|doing|company|position)|working on|what does (he|mayank) do|currently"):
        return "job:" + P["experience"][0]["company"], current_role()
    if _has(t, r"experience|work history|career|worked|jobs?|employ|companies|background|journey"):
        return "experience", experience_overview()

    if _has(t, r"\b(skill|skills|stack|tech|technologies|tools|expertise|strong at|good at)\b"):
        return "skills", skills_overview()
    if _has(t, r"projects?|built|portfolio|side project|open source|repos?"):
        return "projects", projects_overview()
    if _has(t, r"^(who is|tell me about|about|introduce|summar|overview|bio)|who (is|are) (he|you|mayank)|^about"):
        return "about", about()
    return None, None


def is_about_mayank(text, memory):
    t = text.lower()
    if re.search(_NAMED, t):
        return True
    return bool(memory.get("portfolio_agent"))


def answer(text, memory):
    """Markdown answer about Mayank, or None to let the rest of PyBot reply."""
    if not isinstance(text, str) or not text.strip() or not is_about_mayank(text, memory):
        return None
    agent = memory.get("portfolio_agent") or "welcome"
    topic, reply = _route(text, agent, memory.get("portfolio_last"))
    if reply is None:
        # Named but unmatched ("what does mayank think of rust?") -> an honest pointer, not a guess.
        if re.search(_NAMED, text.lower()) or re.search(_PRONOUN, text.lower()) and memory.get("portfolio_agent"):
            if re.search(r"\b(he|his|him|mayank)\b", text.lower()):
                topic, reply = "unknown", (f"That isn't in {FIRST}'s CV, so I won't guess. Try asking about his experience, "
                                           f"skills, projects or services, or email [{EMAIL}](mailto:{EMAIL}).")
        if reply is None:
            return None
    memory["portfolio_last"] = topic
    memory["portfolio_suggestions"] = _suggestions(topic, agent)
    return reply


def _suggestions(topic, agent):
    base = list(SUGGEST.get(agent, SUGGEST["welcome"]))
    kind = (topic or "").split(":")[0]
    extra = {
        "job": ["Tell me more", "Show his impact in numbers", "What are his strongest skills?"],
        "project": ["Tell me more", "List his projects", "What stack does he prefer?"],
        "experience": ["Tell me more", "What is he working on now?", "Show his impact in numbers"],
        "fit": ["Why should we hire him?", "How do I contact him?", "Summarise his experience"],
        "skills": ["Does he know Kubernetes?", "What about AI and RAG?", "Show his impact in numbers"],
        "services": ["How does an engagement work?", "How do I get a quote?", "List his projects"],
    }.get(kind)
    out = []
    for s in (extra or []) + base:
        if s not in out:
            out.append(s)
    return out[:3]
