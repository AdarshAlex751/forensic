"""Feedback slice (Person 1): questions for the detective about the analysis so far.

A fair, senior-investigator critic (Groq) reads Person 3's analysis (persons, edges, contradictions) and the evidence
events they cite, and writes questions that challenge assumptions, raise alternatives, ask what would confirm or
disprove a finding, flag weak or tainted evidence, and point at gaps. It only asks: no answers, no verdicts, no
labels. Every question cites real ids; code drops any that does not.

  contract.py   shared shapes (input bundle, question, feedback.json) and paths
  context.py    builds the input bundle from Person 3's outputs + evidence events (agent A)
  critic.py     system prompt, Groq call, mock and recorded fallback (agent B)
  check.py      validates questions, drops bad ones, writes feedback.json (agent C)
  router.py     GET /api/feedback (agent C)
  run.py        run(case_id): context -> critic -> check -> write
"""
