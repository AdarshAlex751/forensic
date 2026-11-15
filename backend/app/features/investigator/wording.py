"""The wording rule: the investigator reports what the records show and where they disagree. It never labels a
person's role in the crime and never speaks of intent, motive, deception or fault; a human draws those conclusions.
Applied to hypotheses, their "what would disprove it", notes, and the model's evidence requests."""
import re

BANNED = re.compile(
    r"\b(guilty|culprit|perpetrator|thief|criminal|committed the|responsible for the"
    r"|lie[sd]?|lying|liar|false statement|is false|was false|untrue"
    r"|deliberate(?:ly)?|intentional(?:ly)?|motive|conceal\w*|cover[- ]?up|hid(?:e|ing|den)? (?:it|the|his|her|their)"
    r"|spoof\w*|fabricat\w*|tamper\w*|steal|stole|stolen|theft|exfiltrat\w*|sabotag\w*|possibly to|in order to)\b",
    re.I,
)
