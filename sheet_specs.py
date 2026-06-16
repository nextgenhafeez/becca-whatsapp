"""All document types PlayDoc can generate, plus WhatsApp command routing.
This data-driven registry is also the seed of the Phase-3 'template engine'."""
import re

SUBTITLE = "Early Learning & Childcare Diploma  ·  Term 3"

FRAMEWORK_SYSTEM = (
    "You are Rebecca, a real Early Childhood Education student on a field placement in "
    "Alberta, Canada. You are writing your own documentation by hand, in your own words, "
    "grounded in the FLIGHT framework (Well-being; Play and Playfulness; Communication and "
    "Literacies; Diversity and Social Responsibility).\n\n"

    "THE MOST IMPORTANT RULE: your instructor cancels any work that sounds like AI wrote "
    "it. She wants VERY simple English. If the words sound even a little bit like AI, if "
    "there are too many dashes, or if the vocabulary is fancy, she calls the student out. "
    "So you must write in the plainest, simplest English possible.\n\n"

    "HOW REBECCA WRITES (copy this voice exactly):\n"
    "- Short, simple sentences. One idea per sentence. Use everyday words a 13-year-old "
    "would know.\n"
    "- NEVER use an em dash (—) or an en dash (–). Not even once. Use a period or a comma "
    "or the word 'and' instead. This is a hard rule.\n"
    "- No fancy or academic vocabulary. Say 'use' not 'utilize', 'help' not 'facilitate', "
    "'show' not 'demonstrate', 'let' not 'enable', 'about' not 'regarding', 'make' not "
    "'create' when you can, 'big' not 'significant'. Plain words always.\n"
    "- Use soft, open-ended phrasing like Rebecca does: 'Children may...', 'Some children "
    "may...', 'Children might...', 'This experience supports...', 'Children are invited "
    "to...'. It is okay to repeat these simple sentence starters.\n"
    "- Canadian spelling: colour, behaviour, centred, favour, recognize.\n"
    "- Warm, honest, first person where it fits. It should feel like a caring student "
    "wrote it quickly by hand, not a polished essay.\n\n"

    "BANNED words and phrases (never use any of these): furthermore, moreover, "
    "additionally, however (start of sentence), it is important to note, in conclusion, "
    "delve, tapestry, showcase, foster a love of, plays a crucial role, a testament to, "
    "holistic approach (as filler), multifaceted, leverage, utilize, facilitate, "
    "fostering, cultivate, robust, seamless, vibrant, myriad, plethora, navigate (figured), "
    "embark, realm, landscape (figured), underscore, pivotal, intricate, nuanced.\n\n"

    "ECE words you MAY use, but plainly and not too often: big idea, open-ended, "
    "child-centred, process, dispositions, holistic play-based goals, invitation to play, "
    "provocation, FLIGHT. Use them the simple way a student would, never to sound smart.\n\n"

    "Base everything on the photo and the educator's note. Be specific and concrete about "
    "what you actually see. Never invent details that go against the note. Keep each "
    "answer short but complete, about 2 to 4 simple sentences."
)

# (field key, exact question / heading text)
AOR_FIELDS = [
    ("why_observation", "Why are you doing this observation? (Think about where in the planning cycle you are.)"),
    ("who_players", "Who are the players in this observation?"),
    ("objective_observation", "What did the child/children experience and explore? Write a detailed objective observation:"),
    ("prior_learning", "What do you think was the children's learning before this observation? Is this a new emergence of play, and where has it come from?"),
    ("extend_big_idea", "How could you respond to the children and extend this play? What is a possible big idea?"),
    ("first_thoughts", "What were your first thoughts about what the children were doing? What impressions do you have?"),
    ("appear_to_know", "What does the child/children appear to know? What theories about their world do they already have?"),
    ("trying_to_accomplish", "What do you think the child was trying to accomplish in their play? What questions did they need to answer for themselves?"),
    ("wonder_statements", "What questions arise for you? What are your “I wonder” statements?"),
    ("constructivism", "How do the principles of constructivism (hands-on learning) apply to what you saw, and to your course work?"),
    ("dispositions", "What dispositions did you see children nurturing? How can you nurture those dispositions further?"),
]

FCPS_FIELDS = [
    ("selected_category", "Selected category (e.g. Science, Technology, Engineering, Math, Literacy):"),
    ("selected_subcategory", "Selected subcategory:"),
    ("play_or_extension", "Is this a Play Experience or an Extension from the week before?"),
    ("name_of_experience", "Name of the Play Experience:"),
    ("materials_instructions", "Materials and Instructions for the Play Experience (include the plan for when and where you will do this):"),
    ("intent_goals", "Intent of the Play Experience: describe your goals and how this experience nurtures children's learning dispositions (give at least two areas of intent):"),
    ("holistic_goal", "What Holistic Play-Based Goal did you focus on and how was it explored? (FLIGHT 3.1 — Well-being; Play & Playfulness; Communication & Literacies; Diversity & Social Responsibility)"),
]

PPP_FIELDS = [
    ("is_type", "Is this an Invitation to Play, Proposal OR Provocation?"),
    ("big_idea", "Possible big idea observed previously:"),
    ("plan_when_where", "Invitation to Play / Proposal / Provocation planned: include the plan for when and where you will do this:"),
    ("intent", "Intent: what are you looking for? What do you hope to see?"),
    ("observation_revisited", "Observation revisited: was your theory about the possible interest correct? Why or why not? How could you evolve/expand on the interest? Are there common threads in your invitations/provocations this week?"),
] + AOR_FIELDS

BOARD_FIELDS = [
    ("brainstorm_cloud", "Brainstorming Cloud (write 80–100 words on the chosen topic, keeping STEM principles in mind):"),
    ("flowchart", "Flowchart of play experiences — 5 categories, each with about 10 subcategories. Format each line as 'Category: sub1, sub2, sub3, …':"),
]

ESSAY1_Q = ("What does it mean to be a citizen? Think about the rights and responsibilities we have as we "
            "engage with others and our societies. How do our rights and responsibilities differ from those "
            "of children? How are they the same? How does understanding agency, citizenship, and sustainability "
            "change the way you interact with children in your care and your overall professional practice?")
ESSAY2_Q = ("The last few courses of this term taught about the importance of honoring families, recognizing an "
            "individual's identity, and anti-bias practices. Give 3 examples of how you have practiced this in "
            "your role with children. Be sure to pull meaningful connections to your theory and textbooks.")
ESSAY3_Q = ("What are the three biggest concepts you have taken away from your field placement programming? How "
            "has this process helped you see children as learners and the process they take as they engage in "
            "exploration and inquiry about their world? Back up your answer with previous readings and texts.")

SHEETS = {
    "aor":  {"title": "Authentic Observation & Reflection", "mode": "fields", "needs_photo": True,  "fields": AOR_FIELDS,  "system": FRAMEWORK_SYSTEM},
    "fcps": {"title": "Flowchart Planning Sheet",          "mode": "fields", "needs_photo": False, "fields": FCPS_FIELDS, "system": FRAMEWORK_SYSTEM},
    "ppp":  {"title": "PPP + Observation Sheet",           "mode": "fields", "needs_photo": True,  "fields": PPP_FIELDS,  "system": FRAMEWORK_SYSTEM},
    "board":{"title": "Pedagogical Documentation Board",   "mode": "fields", "needs_photo": False, "fields": BOARD_FIELDS,"system": FRAMEWORK_SYSTEM},
    "essay1": {"title": "Reflective Question 1 — Citizenship, Agency & Sustainability", "mode": "prose", "needs_photo": False, "question": ESSAY1_Q, "system": FRAMEWORK_SYSTEM},
    "essay2": {"title": "Reflective Question 2 — Families, Identity & Anti-Bias",        "mode": "prose", "needs_photo": False, "question": ESSAY2_Q, "system": FRAMEWORK_SYSTEM},
    "essay3": {"title": "Reflective Question 3 — Field-Placement Concepts",             "mode": "prose", "needs_photo": False, "question": ESSAY3_Q, "system": FRAMEWORK_SYSTEM},
}

HELP_TEXT = (
    "\U0001F44B Hi! I'm *PlayDoc*. I turn a photo + a short note into a finished, formatted sheet.\n\n"
    "\U0001F4DD *Observation (AOR)* — just send a PHOTO + note (this is the default)\n"
    "\U0001F9E9 *Planning sheet* — type *plan* + your idea (e.g. “plan science, building with blocks”)\n"
    "\U0001F3A8 *PPP + observation* — send a PHOTO + note starting with *ppp*\n"
    "\U0001F5BC️ *Documentation board* — type *board* + your topic\n"
    "\U0001F4AD *Reflective essays* — type *essay1*, *essay2*, or *essay3* (add your own notes after)\n\n"
    "Tip: add the week and big idea in your note, e.g. “week 2, big idea: literacy”."
)

_TABLE = {
    "aor": "aor", "obs": "aor", "observation": "aor",
    "fcps": "fcps", "plan": "fcps", "planning": "fcps",
    "ppp": "ppp",
    "board": "board", "cloud": "board",
}


def route(note: str):
    """Return (sheet_key | 'help' | None, remaining_note). Detects the command word
    anywhere in the message, not just at the start."""
    t = (note or "").strip()
    low = t.lower()
    if low in ("help", "menu", "hi", "hello", "start", "?"):
        return ("help", "")

    # Essays (essay1 / essay 2 / e3) anywhere in the text
    m = re.search(r"\bessay\s*([123])\b|\be([123])\b", low)
    if m:
        num = m.group(1) or m.group(2)
        ctx = re.sub(r"\bessay\s*[123]\b|\be[123]\b", "", t, flags=re.I).strip()
        return (f"essay{num}", ctx)

    # Other commands anywhere (whole-word match)
    for word, key in [("planning", "fcps"), ("plan", "fcps"), ("fcps", "fcps"),
                      ("ppp", "ppp"), ("board", "board"), ("cloud", "board"),
                      ("observation", "aor"), ("aor", "aor")]:
        if re.search(rf"\b{word}\b", low):
            ctx = re.sub(rf"\b{word}\b", "", t, flags=re.I).strip()
            return (key, ctx)

    return (None, t)


def sections_for(spec: dict, data: dict):
    """Build (heading, body) pairs for the document."""
    if spec["mode"] == "prose":
        return [(spec["question"], data.get("essay", ""))]
    return [(label, data.get(key, "")) for key, label in spec["fields"]]
