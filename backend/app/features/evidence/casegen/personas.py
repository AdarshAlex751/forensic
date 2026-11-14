"""Voices and conversation templates for the comms builder (comms.py). Pure data, no randomness here.

A Persona describes how one person writes: Slack habits (lowercase texting, dropped full stops, typos, emoticons,
exclamation marks, clipping to one sentence) and email habits (greeting, sign-off, formality). The cast has
hand-written personas; background people reuse a few voice archetypes.

Templates are threads: a list of turns, each turn a role ("A", "B", "C") and text variants. Placeholders:
  {A} {B} {C}      first name of the person in that role          {Afull} {Bfull}  full name
  {day} {day2}     a weekday name one to three workdays ahead      {slot} {slot2}   times like 10:30 / 12:00
  {topic} {topic2} an engineering work item                      {n} {m}          small numbers
  {talk}           a summit session                               {food}           a lunch place
  {org} {Borg}     tenant organisation names
Hard rules (CASE.md, comms.py guards): Slack text has no double quote, backslash or newline; nothing in a noise
template refers to the incident, the stolen files, removable storage, badges being copied, the corridor camera,
the Northline money, or who left the floor when on the incident evening.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Persona:
    pid: str
    voice: str                      # archetype name, for the report
    lower: float = 0.0              # Slack: chance the whole message is lowercased
    drop_period: float = 0.0        # Slack: chance a trailing full stop is dropped
    typo: float = 0.0               # Slack: chance of one swapped-letter typo
    exclaim: float = 0.0            # Slack: chance a trailing full stop becomes ! (or !!)
    emoji: tuple[str, ...] = ()     # Slack: ASCII emoticons / :shortcodes:
    emoji_p: float = 0.0
    clip: float = 0.0               # Slack: chance to keep only the first sentence (terse people)
    late: tuple[str, ...] = ("sorry, just saw this.",)
    greet: tuple[str, ...] = ("Hi {to},",)          # email greeting, {to} = first name(s) or 'all'
    sign: tuple[tuple[str, ...], ...] = (("Thanks,", "{first}"),)  # email sign-off blocks
    evening: float = 0.1            # chance of answering from home in the evening
    tags: frozenset[str] = field(default_factory=frozenset)


# ------------------------------------------------------------------------------------------------ voices

ARCHETYPES: dict[str, dict] = {
    "dry": dict(drop_period=0.5, typo=0.03, emoji=(":+1:", ":)"), emoji_p=0.12,
                late=("sorry, missed this.", "sorry, just seeing this."),
                greet=("Hi {to},", "{to},"), sign=(("Thanks,", "{first}"), ("{first}",))),
    "warm": dict(drop_period=0.2, typo=0.03, exclaim=0.35, emoji=(":)", ":sparkles:", ":smile:", ":D"), emoji_p=0.3,
                 late=("oh sorry, just saw this!", "sorry, only seeing this now!"),
                 greet=("Hi {to}!", "Hi {to},"), sign=(("Thanks!", "{first}"), ("Cheers,", "{first}"))),
    "texter": dict(lower=0.9, drop_period=0.9, typo=0.08, emoji=(":sweat_smile:", "lol", ":eyes:"), emoji_p=0.12,
                   late=("sorry just saw this", "oops missed this"),
                   greet=("hey {to},", "Hi {to},"), sign=(("thx", "{first}"), ("{first}",))),
    "organizer": dict(drop_period=0.1, typo=0.01, emoji=(":calendar:", ":white_check_mark:", ":pray:"), emoji_p=0.2,
                      late=("Sorry, catching up on this now.",),
                      greet=("Hi {to},", "Hello {to},"), sign=(("Thanks,", "{first}"), ("Best,", "{first}"))),
    "joker": dict(lower=0.5, drop_period=0.6, typo=0.05, emoji=(":joy:", ":laughing:", "haha", ":upside_down_face:"),
                  emoji_p=0.22, late=("sorry, just saw this", "ah missed this, sorry"),
                  greet=("Hey {to},", "Hi {to},"), sign=(("Cheers,", "{first}"), ("{first}",))),
    "manager": dict(drop_period=0.1, typo=0.01, exclaim=0.15, emoji=(":pray:", ":+1:", ":tada:"), emoji_p=0.18,
                    late=("Sorry, just catching up here.",),
                    greet=("Hi {to},", "Hello {to},"), sign=(("Thanks,", "{first}"), ("Best,", "{first}"))),
    "external_formal": dict(greet=("Hi {to},", "Hello {to},", "Dear {to},"),
                            sign=(("Best regards,", "{full}", "{org}"), ("Kind regards,", "{full}"))),
    "external_casual": dict(greet=("Hi {to},", "Hey {to},"), sign=(("Thanks!", "{first}"), ("Cheers,", "{first}"))),
}

# Cast personas (CASE.md section 3 and the brief from the team).
CAST: dict[str, Persona] = {
    "p_hank": Persona(
        "p_hank", "terse, clipped, guarded", typo=0.02, clip=0.6,
        late=("Missed this. Sorry.", "Just saw this."),
        greet=("{to},",), sign=(("Hank",), ("H.",)), evening=0.25, tags=frozenset({"hal", "eng"})),
    "p_maggie": Persona(
        "p_maggie", "friendly, chatty, exclamation marks", typo=0.04, exclaim=0.6,
        emoji=(":)", ":D", ":tada:", ":heart:", ":smile:", "<3"), emoji_p=0.35,
        late=("ahh sorry, just saw this!", "sorry sorry, only seeing this now!"),
        greet=("Hi {to}!", "Hey {to}!"), sign=(("Thanks so much!", "Maggie"), ("xx", "Maggie"), ("Cheers!", "Maggie")),
        evening=0.3, tags=frozenset({"hal", "eng"})),
    "p_alma": Persona(
        "p_alma", "formal, precise, full name and title", late=("Apologies for the delay in replying.",),
        greet=("Dear {to},", "Good morning {to},"),
        sign=(("Kind regards,", "Alma Imhoff", "Head of Security, Halvorsen Dynamics"),
              ("Regards,", "Alma Imhoff", "Head of Security, Halvorsen Dynamics")),
        evening=0.05, tags=frozenset({"hal", "sec"})),
    "p_frederik": Persona(
        "p_frederik", "short IT notices, ticket numbers, plain wording",
        greet=("Hello,", "Hi {to},"),
        sign=(("Regards,", "Frederik Mendelssohn", "Ostrander IT, floor IT support"),
              ("Frederik", "Ostrander IT")), tags=frozenset({"it"})),
    "p_kim": Persona("p_kim", "polished recruiter", tags=frozenset({"kim"})),
    "p_bg_17": Persona(
        "p_bg_17", "practical lab scheduling", drop_period=0.3, typo=0.03, emoji=(":test_tube:", ":+1:"),
        emoji_p=0.08, late=("sorry, was in the lab. just saw this.", "sorry, had gloves on. just seeing this."),
        greet=("Hi {to},",), sign=(("Thanks,", "Rina"), ("Rina Okafor", "Lab technician, Halvorsen Dynamics")),
        evening=0.05, tags=frozenset({"hal", "lab"})),
}

# Halvorsen background people with Slack: archetype + tags.
BG_HALVORSEN = {
    "p_bg_01": ("dry", {"hal", "eng", "lab"}),        # Theo Lindqvist
    "p_bg_02": ("warm", {"hal", "eng", "lab"}),       # Amara Okonkwo
    "p_bg_03": ("texter", {"hal", "eng"}),            # Jonah Feld
    "p_bg_04": ("organizer", {"hal", "pm"}),          # Leila Haddad
    "p_bg_05": ("joker", {"hal", "eng", "lab"}),      # Marcus Bell
    "p_bg_06": ("manager", {"hal", "ops"}),           # Sofia Marchetti
}

ORGS = {
    "halvorsen.example": "Halvorsen Dynamics",
    "corvane.example": "Corvane Labs",
    "brightwater.example": "Brightwater Analytics",
    "quillfeather.example": "Quillfeather Bio",
    "tessaract.example": "Tessaract Robotics",
    "lumenpolicy.example": "Lumen Policy Group",
    "ostrander-it.example": "Ostrander IT",
    "mercer-machining.example": "Mercer Machining",
    "jrr-aisummit.example": "JRR AI Summit",
    "jrr-facilities.example": "JRR Building Facilities",
}

# Mailing lists and external senders (all fictional *.example).
L_ALL = "halvorsen-all@halvorsen.example"
L_ENG = "halvorsen-eng@halvorsen.example"
L_TENANTS = "jrr2-tenants@ostrander-it.example"
L_SUMMIT = "jrr2-members@jrr-aisummit.example"
SUMMIT = ("events@jrr-aisummit.example", "JRR AI Summit")
FACILITIES = ("dana.whitlock@jrr-facilities.example", "Dana Whitlock")
FACILITIES2 = ("ravi.castellanos@jrr-facilities.example", "Ravi Castellanos")
SHOP = ("orders@mercer-machining.example", "Mercer Machining Orders")

# ------------------------------------------------------------------------------------------------ fillers

TOPICS = [
    "nozzle thermal model", "vibration test plan", "CFD mesh refinement", "bracket FEA", "harness drawing rev C",
    "telemetry parser", "test stand DAQ config", "valve timing sweep", "feed line sizing", "mass budget sheet",
    "thermal vacuum checklist", "flight software unit tests", "sensor calibration script", "mounting plate redesign",
    "power budget", "requirements matrix", "interface control doc", "pressure transducer drift", "fixture drawings",
    "test report template",
]
TALKS = [
    "autonomy in orbit", "LLMs for test automation", "edge inference on small satellites", "safety cases for ML",
    "robot learning on a budget", "the AI policy panel", "foundation models for sensor data",
    "digital twins for test labs", "data provenance in ML pipelines", "human factors in autonomous systems",
]
# Summit programme per day (matches the daily summit emails in comms.py): (session, start time).
PROGRAM = {
    "2026-03-02": [("the opening keynote", "10:00"), ("autonomy in orbit", "14:00"), ("the poster session", "16:00")],
    "2026-03-03": [("LLMs for test automation", "10:30"), ("edge inference on small satellites", "14:00")],
    "2026-03-04": [("safety cases for ML", "10:00"), ("the AI policy panel", "13:30")],
    "2026-03-05": [("digital twins for test labs", "10:00"), ("robot learning on a budget", "14:30")],
    "2026-03-06": [("data provenance in ML pipelines", "10:00"), ("the closing session", "15:00")],
}
FOOD = ["the noodle place", "the falafel cart", "the salad bar downstairs", "the dumpling spot", "the deli on the corner",
        "the ramen place", "the burrito place", "the cafe in the atrium"]

# ------------------------------------------------------------------------------------------------ Slack threads
# Each: channel, id, roles {role: tag}, turns [(role, [variants])], optional days ('weekday', 'weekend', 'fri',
# 'mon', 'pre_summit', 'summit', 'pre_0302'), weight, evening (True = may happen 19:30-22:00 from home).

SLACK_THREADS: list[dict] = [
    # ---------------- general
    dict(ch="general", id="printer", roles={"A": "hal", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Printer by the kitchen is jammed again.", "Anyone else getting paper jam errors on the floor printer?",
               "The printer is showing tray 2 jam again."]),
        ("B", ["Yep, tray 2 is stuck. I left a note on it.", "Same here. Printed to the one by the lounge instead.",
               "Yes, it ate my boarding pass printout earlier."]),
        ("C", ["I emailed IT about it this morning.", "Ticket is in with IT, they said the copier vendor is coming.",
               "Lounge printer works fine for now."]),
        ("A", ["Thanks, lounge one it is.", "Ok, thanks.", "Good to know, thanks."]),
    ], weight=2),
    dict(ch="general", id="wifi_slow", roles={"A": "hal", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Is the wifi crawling for anyone else in 217?", "Wifi is really slow right now, just me?"]),
        ("B", ["Not just you. Video call keeps freezing.", "Slow here too.", "Same. Switched to the ethernet port."]),
        ("C", ["Seems better now.", "Back to normal for me.", "Picked up again a minute ago."]),
    ], weight=1.2),
    dict(ch="general", id="coffee", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Coffee machine is descaling, back in about 20 minutes.", "Someone finished the oat milk and did not replace it. I forgive you.",
               "New coffee beans in the kitchen, the dark roast is back."]),
        ("B", ["Thank you for the public service announcement.", "Noted. Tea it is.", "Best news of the day."]),
    ], weight=1.5),
    dict(ch="general", id="lunch", hours=(10.5, 12.2), roles={"A": "hal", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Lunch at {slot}? Thinking {food}.", "Anyone up for {food} at {slot}?", "Going to {food} around {slot} if anyone wants to come."]),
        ("B", ["In.", "Count me in.", "Yes please, I have a call until {slot} though, will catch up."]),
        ("C", ["I brought food but I will come sit with you.", "Can't today, enjoy.", "In, meet at the elevators?"]),
        ("A", ["Great, see you then.", "Elevators at {slot} then.", "Perfect."]),
    ], weight=3),
    dict(ch="general", id="meeting_room", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Is anyone using the small meeting room in 217 at {slot}?", "Need the 217 meeting room for half an hour at {slot}, anyone have it?"]),
        ("B", ["All yours.", "I have it until {slot}, then it is free.", "I booked it but can move to the lounge, take it."]),
        ("A", ["Thanks!", "Thank you, I owe you one.", "Appreciated."]),
    ], weight=2),
    dict(ch="general", id="package", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Package for {B} at the front desk.", "{B}, there is a box with your name on it by the kitchen.",
               "{B} your delivery is at reception."]),
        ("B", ["Thanks! Grabbing it now.", "Oh nice, that is the new monitor arm. Thanks.", "Thank you, on my way."]),
    ], weight=1.5),
    dict(ch="general", id="cake", roles={"A": "hal", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Leftover cake in the kitchen, help yourselves :cake:", "There are bagels in the kitchen from the morning meeting.",
               "Brought cookies, they are on the counter."]),
        ("B", ["You are a hero.", "Thank you!", "On my way."]),
        ("C", ["Already had two. No regrets.", "This made my afternoon.", "Saving one for later."]),
    ], weight=1.5),
    dict(ch="general", id="cold", roles={"A": "hal", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Is it freezing in 217 or is it just me?", "The heating in 217 seems off today.",
               "Anyone else wearing their coat indoors today?"]),
        ("B", ["It is not just you.", "Freezing. I am typing with gloves on.", "Very cold by the windows."]),
        ("C", ["Facilities said the heating is being adjusted this week.", "I think facilities are working on the air handler.",
               "Space heater is under my desk if anyone wants to borrow it."]),
    ], weight=1.2, days="pre_0302"),
    dict(ch="general", id="weather", hours=(8.7, 11.0), roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Roads are slick this morning, take it easy coming in.", "Snow is supposed to start around {slot}, heads up.",
               "Sidewalk by the main entrance is icy, careful."]),
        ("B", ["Thanks for the heads up.", "Noted, taking the bus today.", "Thanks, almost slipped earlier."]),
    ], weight=0.8),
    dict(ch="general", id="fridge", roles={"A": "ops", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Kitchen fridge clean out on Friday at 3. Anything unlabeled goes.", "Reminder: please label your food in the shared fridge, it gets cleared Friday."]),
        ("B", ["Is the yogurt with no name a casualty?", "Labeling my soup right now."]),
        ("A", ["The yogurt is a casualty.", "Thank you!"]),
        ("C", ["Rest in peace, yogurt.", "Same, labeling mine now."]),
    ], weight=0.8, days="weekday"),
    dict(ch="general", id="supplies", roles={"A": "ops", "B": "hal"}, turns=[
        ("A", ["Office order goes out today. Need anything? Pens, notebooks, chargers?", "Placing the supply order this afternoon, reply here with requests."]),
        ("B", ["A spare laptop charger for the meeting room would be great.", "Whiteboard markers that actually work, please.",
               "Sticky notes, the big ones."]),
        ("A", ["Added.", "On the list.", "Done, should arrive {day}."]),
    ], weight=0.8, days="weekday"),
    dict(ch="general", id="kudos", roles={"A": "ops", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Shout out to {B} for turning the {topic} around so quickly this week.", "Big thanks to {B} for jumping in on the {topic}."]),
        ("B", ["Thanks, it was a team effort.", "Thank you! Could not have done it without {C}."]),
        ("C", [":clap:", "Well deserved.", "Agreed, great work."]),
    ], weight=1),

    # ---------------- halvorsen-eng
    dict(ch="halvorsen-eng", id="review", roles={"A": "eng", "B": "eng"}, turns=[
        ("A", ["Can someone review my PR for the {topic}?", "PR for the {topic} is up, would love a second pair of eyes.",
               "Small PR for the {topic}, should take ten minutes."]),
        ("B", ["Looking now.", "I can take it after standup.", "On it."]),
        ("B", ["Left a couple of comments, nothing big.", "Looks good, one question about the units on line 40.",
               "Approved. Minor nit about naming."]),
        ("A", ["Thanks, fixed.", "Good catch, updated.", "Thanks, merging."]),
    ], weight=3),
    dict(ch="halvorsen-eng", id="sim", roles={"A": "eng", "B": "eng", "C": "eng"}, turns=[
        ("A", ["{topic} run finished overnight, results are in the team folder.", "Sweep for the {topic} is done, {n} of {m} cases converged."]),
        ("B", ["Nice. Residuals look ok?", "Which case diverged?"]),
        ("A", ["Mostly. One case diverged, rerunning it with a smaller step.", "Case {n}. Probably the boundary condition, checking."]),
        ("C", ["Ping me if you want help with the mesh.", "I saw the same thing last month, try halving the time step.", "Thanks for running these."]),
    ], weight=3),
    dict(ch="halvorsen-eng", id="design_review", roles={"A": "pm", "B": "eng", "C": "eng"}, turns=[
        ("A", ["Design review for the {topic} moved to {day} at {slot}, same room.", "Heads up: {topic} review is {day} {slot}. Slides by the day before please."]),
        ("B", ["Works for me.", "Can we push it 30 minutes? I have a call.", "Ok, will have slides ready."]),
        ("A", ["Pushed to {slot2}.", "Sure, {slot2} it is.", "Thanks."]),
        ("C", ["Fine by me.", ":+1:", "Works."]),
    ], weight=2.5),
    dict(ch="halvorsen-eng", id="build", roles={"A": "eng", "B": "eng"}, turns=[
        ("A", ["Main build is red, looks like the {topic} tests.", "CI is failing on main since this morning, anyone touching the {topic}?"]),
        ("B", ["My bad, reverting.", "That was me, fix incoming.", "Looking."]),
        ("B", ["Green again.", "Should be fixed now.", "Reverted, rerunning CI."]),
        ("A", ["Thanks.", "Confirmed green.", "Thanks for the quick fix."]),
    ], weight=2),
    dict(ch="halvorsen-eng", id="whereis", roles={"A": "eng", "B": "eng"}, turns=[
        ("A", ["Does anyone have the latest {topic} spreadsheet?", "Where do we keep the {topic} notes now?",
               "Which version of the {topic} is current?"]),
        ("B", ["It is pinned in the channel.", "Team folder, under {topic}.", "The one from last week, I renamed the old one."]),
        ("A", ["Found it, thanks.", "Got it.", "Thanks, that saved me some digging."]),
    ], weight=2),
    dict(ch="halvorsen-eng", id="standup", roles={"A": "pm", "B": "eng"}, turns=[
        ("A", ["Standup moved to 10:15 today.", "Standup is async today, drop your update in the thread.",
               "Quick standup at 9:45, ten minutes max."]),
        ("B", ["Ok.", "Update: finishing the {topic}, then reviews.", "Got it."]),
    ], weight=2, days="weekday", hours=(8.7, 10.0)),
    dict(ch="halvorsen-eng", id="parts", roles={"A": "eng", "B": "eng", "C": "eng"}, turns=[
        ("A", ["Bracket samples arrived from the machine shop.", "Second batch of fixtures came in from Mercer this morning."]),
        ("B", ["Measure the bore before we sign off please.", "Did they fix the chamfer this time?"]),
        ("A", ["Within tolerance on all {n}.", "Yes, chamfer is right. One part has a scratch, sending it back."]),
        ("C", ["Great, I will update the {topic}.", "Nice, that unblocks the fit check."]),
    ], weight=1.2),
    dict(ch="halvorsen-eng", id="question", roles={"A": "eng", "B": "eng"}, turns=[
        ("A", ["Quick question: are we still using the old units convention in the {topic}?", "Do we have a template for the {topic}?",
               "Is anyone else seeing slow file sync on the team folder?"]),
        ("B", ["SI everywhere now, the old sheets are wrong.", "Yes, it is in the templates folder.", "A bit slow, yes. It catches up after a few minutes."]),
        ("A", ["Thanks.", "Perfect.", "Ok, good to know."]),
    ], weight=2),
    dict(ch="halvorsen-eng", id="weekly", roles={"A": "pm", "B": "eng", "C": "eng"}, turns=[
        ("A", ["Eng weekly notes are due at 4, please add your bullets.", "Reminder: weekly update doc closes at 4 today."]),
        ("B", ["Done.", "Added mine.", "Will do after this meeting."]),
        ("C", ["Mine are in.", "Done, sorry they are long.", "Adding now."]),
    ], weight=3, days="fri"),
    dict(ch="halvorsen-eng", id="pairing", roles={"A": "eng", "B": "eng"}, turns=[
        ("A", ["{B}, do you have 20 minutes to pair on the {topic} this afternoon?", "Anyone free to sanity check my {topic} numbers?"]),
        ("B", ["Sure, {slot}?", "Tomorrow morning works.", "Give me ten minutes."]),
        ("A", ["{slot} works.", "Great, tomorrow then.", "Ok, ping me."]),
    ], weight=2),

    # ---------------- lab-219
    dict(ch="lab-219", id="book", roles={"A": "lab_user", "B": "rina"}, turns=[
        ("A", ["Can I book 219 on {day} {slot} to {slot2} for a calibration run?", "Is 219 free {day} morning? Need the bench for about two hours.",
               "Could I get the test bench in 219 {day} from {slot}?"]),
        ("B", ["Booked. Please leave the bench as you found it.", "You have it {slot} to {slot2}. Logbook is on the shelf.",
               "Done, it is on the schedule."]),
        ("A", ["Will do, thanks.", "Thanks Rina.", "Perfect, thank you."]),
    ], weight=3, days="weekday"),
    dict(ch="lab-219", id="calibration", roles={"A": "rina", "B": "lab_user"}, turns=[
        ("A", ["Load cell calibration is due this week, I will run it {day} morning.", "Running the pressure gauge calibration at {slot}, bench is busy for an hour.",
               "Calibration on the thermocouple reader is done, offsets are in the binder."]),
        ("B", ["Thanks Rina.", "Great, I will plan around it.", "Thanks for keeping on top of this."]),
        ("A", ["Np, will post here when it is done.", "Will post when it is done.", "All within spec this time."]),
    ], weight=2.5, days="weekday"),
    dict(ch="lab-219", id="consumables", roles={"A": "rina", "B": "lab_user"}, turns=[
        ("A", ["We are low on nitrile gloves and isopropyl, ordering today.", "Ordering lab consumables this afternoon, anything to add?"]),
        ("B", ["Can you add zip ties and kapton tape?", "Lint free wipes please.", "Small hex keys, we keep losing them."]),
        ("A", ["Added.", "On the order.", "Added, should be here {day}."]),
    ], weight=1.5, days="weekday"),
    dict(ch="lab-219", id="tidy", roles={"A": "rina", "B": "lab_user"}, turns=[
        ("A", ["Whoever used the scope last, please put the probes back in the drawer.", "Please do not leave coffee cups on the bench, thanks.",
               "Torque wrench goes back in its case after use please."]),
        ("B", ["Sorry, that was me.", "Will remind the team.", "My fault, fixed."]),
        ("A", ["No worries.", "Thanks.", "Np, thanks."]),
    ], weight=1.5, days="weekday"),
    dict(ch="lab-219", id="humidity", roles={"A": "rina", "B": "lab_user"}, turns=[
        ("A", ["Humidity in 219 was a bit high this morning, keep the door closed during runs.", "Fume hood filter was changed today, airflow is back to normal."]),
        ("B", ["Noted.", "Thanks, good to know.", "Ok."]),
    ], weight=1, days="weekday"),
    dict(ch="lab-219", id="results", roles={"A": "lab_user", "B": "lab_user", "C": "rina"}, turns=[
        ("A", ["Vibration table run {n} done, data is on the lab share.", "Test stand run finished, saw a small offset on channel {n}."]),
        ("B", ["Nice, can you send me the raw files?", "Channel {n} was drifting last week too."]),
        ("C", ["Raw files are on the lab share, same folder as last week.", "Might be the cable, I will swap it before the next run."]),
        ("A", ["Thanks Rina.", "That would help, thanks."]),
    ], weight=2, days="weekday"),
    dict(ch="lab-219", id="week_plan", roles={"A": "rina", "B": "lab_user", "C": "lab_user"}, turns=[
        ("A", ["219 this week: Tue morning calibration, Thu vibration table all day, rest is open.", "Lab plan for the week is on the door. Thursday is busy, book early."]),
        ("B", ["Could I grab Friday 10 to 12?", "Can I have Monday afternoon next week?"]),
        ("A", ["Yours.", "Booked."]),
        ("C", ["Thanks for posting this.", ":+1:"]),
    ], weight=3, days="mon"),

    # ---------------- random
    dict(ch="random", id="weekend", roles={"A": "hal", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Any plans for the weekend?", "What is everyone up to this weekend?"]),
        ("B", ["Hiking if the weather holds.", "Painting the hallway, send help.", "Absolutely nothing and I cannot wait."]),
        ("C", ["Visiting my sister in Philly.", "Long run on Saturday and a lot of sleep.", "Finally assembling the bookshelf."]),
        ("A", ["Sounds great.", "Good luck with that.", "Living the dream."]),
    ], weight=3, days="fri"),
    dict(ch="random", id="pets", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["My cat discovered the radiator and has not moved since :cat:", "The dog ate a whole sock this morning. He is fine. I am not."]),
        ("B", ["She looks very pleased with herself. Need a photo of this immediately.", "Classic. Is he ok?"]),
        ("A", ["Photo incoming. She is the boss now.", "He is very proud of himself."]),
    ], weight=1.5, evening=True),
    dict(ch="random", id="show", roles={"A": "hal", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Has anyone watched the new season of that space documentary series?", "Finished the book about the lunar program, highly recommend."]),
        ("B", ["Two episodes in, it is great.", "Can I borrow it when you are done?"]),
        ("C", ["No spoilers please.", "Adding it to my list."]),
    ], weight=1.5, evening=True),
    dict(ch="random", id="snack", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Who brought the stroopwafels?", "Whoever left the clementines by the sink, thank you."]),
        ("B", ["Guilty.", "That was me. Take more."]),
        ("A", ["Bless you.", "Legend."]),
    ], weight=1.5),
    dict(ch="random", id="run", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Anyone up for a run at lunch {day}?", "Lunchtime walk around the lake {day}?"]),
        ("B", ["I am in if it is not raining.", "Yes, slow pace please."]),
        ("A", ["Deal.", "Slow pace guaranteed.", "Feel better."]),
    ], weight=1.2),
    dict(ch="random", id="crossword", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Today's crossword is brutal.", "Seven letters, a small rocket stage. Go."]),
        ("B", ["Stuck on 14 across. Gave up at lunch.", "Booster? Seven letters, fits."]),
        ("A", ["Same.", "Got it, thanks."]),
    ], weight=1.2, evening=True),
    dict(ch="random", id="music", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Need a focus playlist, recommendations?", "Whose phone is playing jazz in the kitchen? It is nice."]),
        ("B", ["Film scores. No lyrics, no distractions.", "Mine, sorry, turning it off."]),
        ("A", ["Trying it now.", "No, leave it on, it is nice."]),
    ], weight=1, evening=True),
    dict(ch="random", id="weekend_home", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Made way too much soup, it is a soup week now.", "Saw a heron by the canal this morning.",
               "Farmers market had the first rhubarb, it is a sign."]),
        ("B", ["Soup week is the best week.", "Nice, they are huge up close.", "Spring is coming."]),
    ], weight=3, days="weekend", evening=True),

    # ---------------- summit-2026
    dict(ch="summit-2026", id="register", roles={"A": "hal", "B": "hal", "C": "hal"}, turns=[
        ("A", ["Summit registration is open, use the member code from the email.", "Did everyone register for the summit yet?"]),
        ("B", ["Registered.", "Doing it now.", "Is the welcome reception included?"]),
        ("C", ["Registered too.", "Same, doing it now.", "Yes, Wednesday evening, it is on the agenda."]),
    ], weight=2, days="pre_summit"),
    dict(ch="summit-2026", id="agenda", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Full summit agenda is out, the {talk} session looks good.", "Anyone looked at the agenda? I want to catch {talk}."]),
        ("B", ["Saw it, I want to go to {talk}.", "Bookmarked a few, will share.", "Booked it in my calendar."]),
    ], weight=2, days="pre_summit"),
    dict(ch="summit-2026", id="talk", needs="next_talk", roles={"A": "hal", "B": "hal", "C": "hal"}, turns=[
        ("A", ["{next_talk} at {next_slot}, anyone going?", "Going to {next_talk} at {next_slot}, anyone joining?"]),
        ("B", ["I will go.", "Save me a seat.", "Can't, in a review. Take notes?"]),
        ("C", ["Me too.", "Will join halfway.", "I went to the earlier one, it was good."]),
        ("A", ["See you there.", "Front left.", "Notes coming."]),
    ], weight=3, days="summit"),
    dict(ch="summit-2026", id="notes", needs="past_talk", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Notes from {past_talk} are in the summit doc.", "Slides from {past_talk} are up on the summit site."]),
        ("B", ["Thanks for sharing.", "Super useful, thanks.", "Reading them now."]),
    ], weight=2.5, days="summit"),
    dict(ch="summit-2026", id="booth", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Tessaract Robotics demo at their booth is worth seeing.", "The poster session in the lobby is better than expected.",
               "Corvane Labs have a neat demo in the lounge."]),
        ("B", ["Going after lunch.", "Thanks, adding it.", "Saw it, the arm is impressive."]),
    ], weight=1.5, days="summit"),
    dict(ch="summit-2026", id="nametag", days="summit_first", roles={"A": "hal", "B": "hal"}, turns=[
        ("A", ["Pick up your summit name tag at the registration desk on the ground floor.", "Lanyards for the summit are at the front desk."]),
        ("B", ["Got mine.", "Thanks!", "Grabbing it now."]),
    ], weight=1),
]

# Kim and Hank: Slack Connect DM noise around the story messages (polished recruiter vs clipped Hank).
KIM_DM_NOISE = [
    # (date, hh, mm, ss, handle, text)
    ("2026-02-25", 18, 40, 0, "kim.sayers", "Hank, good to connect here. Thanks again for making time last week."),
    ("2026-02-25", 19, 36, 20, "hank.gibson", "Sure. Glad it worked out."),
    ("2026-02-27", 12, 10, 0, "kim.sayers", "The offer paperwork is with you now. Let me know if anything needs a second look."),
    ("2026-02-27", 20, 31, 45, "hank.gibson", "Got it. Reading it this weekend."),
    ("2026-03-01", 17, 2, 10, "hank.gibson", "Signed. Sent it back."),
    ("2026-03-01", 17, 19, 30, "kim.sayers", "Wonderful news. Welcome aboard, we are thrilled."),
    ("2026-03-06", 13, 48, 0, "kim.sayers", "Does two o'clock still work for our call today?"),
    ("2026-03-06", 13, 52, 25, "hank.gibson", "Yes."),
]

# Words and patterns that must never appear in noise (comms.py checks every noise message before using it).
FORBIDDEN = [
    r"\busb\b", r"thumb ?drive", r"flash ?drive", r"\bclon", r"coinvault", r"signing bonus", r"camera 3",
    r"cam-03", r"\btitan\b", r"northline", r"\bbadge", r"left together", r"went home", r"bonus",
]

# ------------------------------------------------------------------------------------------------ email threads
# Each: id, roles {role: spec}, subject [variants], turns [{by, to, body: [branch variants of line lists], p}].
# Role specs: a tag (hal, eng, pm, ops, rina, tenant), 'pid:<person_id>' or 'ext:<addr>|<name>'; 'to' may also hold
# 'list:<address>'. One branch index k is drawn per thread so replies match the question (body[k % len(body)]).
# A reply goes to the previous sender; the other people of the previous message are copied.

STATUS = ["on track", "done, in review", "about 70 percent", "blocked on parts, expected {day}", "first draft shared",
          "waiting for test data", "merged", "slipped a few days, new date {day}", "ready for review", "started"]

EMAIL_THREADS: list[dict] = [
    dict(id="room_borrow", weight=1.5, max=4, roles={"A": "tenant", "B": "pid:p_bg_06"},
         subject=["Borrowing the 217 meeting room on {day}", "Meeting room request for {day}"],
         turns=[
             dict(by="A", to=["B"], body=[
                 ["Would it be possible for us to borrow the small meeting room in 217 on {day} from {slot} to {slot2}?",
                  "Our own room is booked out with summit prep and we have a call with partners that afternoon.",
                  "Happy to work around your schedule."],
                 ["Quick favour: could {org} use your meeting room on {day} around {slot} for an hour?",
                  "Ours is being used for interviews all day."]]),
             dict(by="B", body=[
                 ["Of course, the room is free {day} from {slot} to {slot2}.",
                  "I have put {org} on the booking sheet by the door.", "Please leave the whiteboard clean afterwards."],
                 ["Unfortunately {day} is busy for us, but {day2} at {slot} would work.",
                  "Let me know if that helps, otherwise the lounge is usually quiet in the morning."]]),
             dict(by="A", p=0.8, body=[
                 ["Perfect, thank you very much.", "We will keep it tidy."],
                 ["{day2} works for us, thank you for being flexible."]]),
         ]),
    dict(id="question", weight=6, roles={"A": "eng", "B": "eng"},
         subject=["Question about the {topic}", "{topic}: quick check", "Re-check on the {topic} numbers"],
         turns=[
             dict(by="A", to=["B"], body=[
                 ["Before I send the {topic} to Leila, can you confirm we are using the revised load case?",
                  "The numbers in my sheet are about {n} percent off from last week."],
                 ["Do you still have the input files for the {topic}?",
                  "I want to rerun case {n} with the new boundary conditions."],
                 ["I went through the {topic} again and I think the margin on item {n} is too thin.",
                  "Could you take a look when you have a moment?"]]),
             dict(by="B", body=[
                 ["Yes, revised load case. The {n} percent is the new safety factor, that is expected.",
                  "I added a note in the sheet so it does not confuse anyone else."],
                 ["They are in the team folder under runs, next to the {topic2} files.",
                  "Case {n} needs the updated material card too, it is in the same place."],
                 ["Agreed, it is thin. I would bump the wall thickness and rerun.",
                  "Happy to look at it together on {day}."]]),
             dict(by="A", p=0.75, body=[
                 ["Great, that explains it. Thanks."], ["Found them, thanks. Rerunning now."],
                 ["{day} works, I will send an invite."]]),
             dict(by="B", p=0.25, body=[["No problem."], ["Shout if anything looks odd."], ["Sounds good."]]),
         ]),
    dict(id="meeting_notes", weight=3, roles={"A": "eng", "B": "eng", "C": "pm"},
         subject=["Notes: {topic} sync", "{topic} sync notes and actions"],
         turns=[
             dict(by="A", to=["list:" + L_ENG], body=[
                 ["Notes from today's {topic} sync:", "- agreed to freeze the interface on {day}",
                  "- {B} to update the {topic2} by end of week", "- open question on test fixtures, parked for now"],
                 ["Short notes from the {topic} sync:", "- design is ok to move forward",
                  "- {n} action items, owners in the tracker", "- next sync {day} at {slot}"]]),
             dict(by="B", p=0.7, body=[
                 ["Thanks. I will have the {topic2} update by Friday."],
                 ["One correction: the fixture question is mine, not parked."],
                 ["Thanks for writing this up."]]),
             dict(by="C", p=0.5, body=[
                 ["Thanks both. I added the actions to the board."],
                 ["Noted, I will move the review to after the freeze."]]),
         ]),
    dict(id="design_review", weight=3, roles={"A": "pid:p_bg_04", "B": "eng", "C": "eng"},
         subject=["Design review: {topic} on {day} at {slot}", "Invitation: {topic} review ({day})"],
         turns=[
             dict(by="A", to=["list:" + L_ENG], body=[
                 ["The {topic} design review is on {day} at {slot} in the 217 meeting room.",
                  "Please send slides by the day before, ten minutes each.", "Agenda:", "1. status and open risks",
                  "2. test plan", "3. decisions needed"],
                 ["Booking the {topic} review for {day} at {slot}.",
                  "Goal is a go or no-go on the current concept.", "If you cannot make it, send comments in advance."]]),
             dict(by="B", body=[
                 ["Accepted. Could we have 15 minutes for the test plan? It has grown."],
                 ["I have a conflict at {slot}, could we start at {slot2}?"],
                 ["Works for me, slides by tomorrow."]]),
             dict(by="A", p=0.8, body=[
                 ["Fine, 15 minutes for the test plan."], ["Moved to {slot2}, updated invite to follow."],
                 ["Thanks {B}."]]),
             dict(by="C", p=0.4, body=[["Thanks, that works for me too."], ["See you there."]]),
         ]),
    dict(id="lab_request", weight=2.5, max=4, roles={"A": "lab", "B": "pid:p_bg_17"},
         subject=["Room 219 on {day}?", "Calibration before the {topic} test"], no_hank_after=True,
         turns=[
             dict(by="A", to=["B"], body=[
                 ["Could you put me down for the 219 bench on {day} from {slot} to {slot2}?",
                  "It is for the {topic}, nothing hazardous."],
                 ["Is there a slot this week for a calibration check on the pressure transducers?",
                  "I would like to run the {topic} test on {day2}."]]),
             dict(by="B", body=[
                 ["Booked {day} {slot} to {slot2}.", "Bench is clean, logbook is on the shelf by the door."],
                 ["I can do the transducer check on {day} morning.",
                  "Leave them on the shelf with a tag and I will pick them up."]]),
             dict(by="A", p=0.7, body=[["Thanks Rina!"], ["Great, tagged and on the shelf."]]),
         ]),
    dict(id="tenant_whiteboard", weight=1.2, max=2, roles={"A": "tenant", "B": "hal"},
         subject=["Shared whiteboard in the lounge", "Lounge whiteboard"],
         turns=[
             dict(by="A", to=["B"], body=[
                 ["Hi from {org} next door.",
                  "Is the diagram on the lounge whiteboard yours? We would like to use the board on {day}.",
                  "Happy to take a photo of it for you first."]]),
             dict(by="B", body=[
                 ["Yes, that is ours, sorry. I will wipe it this afternoon."],
                 ["Not ours, I think it belongs to the people in 224. Go ahead and take a photo."]]),
             dict(by="A", p=0.7, body=[["Thanks, much appreciated."], ["Will do, thanks."]]),
         ]),
    dict(id="tenant_collab", weight=1.2, max=3, days="to_0305", roles={"A": "tenant", "B": "eng"},
         subject=["Coffee during summit week?", "Intro from {org}"],
         turns=[
             dict(by="A", to=["B"], body=[
                 ["We met briefly at the floor social in January.",
                  "{org} is showing a small demo at the summit and I would love your opinion on the test setup.",
                  "Would a coffee on {day} at {slot} work?"]]),
             dict(by="B", body=[
                 ["Happy to. {day} at {slot} in the lounge works."],
                 ["Sounds fun. {day} is packed, could we do {day2} at {slot}?"]]),
             dict(by="A", p=0.8, body=[["Great, see you then."], ["{day2} at {slot} it is."]]),
         ]),
    dict(id="shop_order", weight=1.2, max=3, roles={"A": "ext:" + SHOP[0] + "|" + SHOP[1], "B": "eng"},
         subject=["Order {n}{m}71 shipped", "Your order {n}{m}71: delivery update"],
         turns=[
             dict(by="A", to=["B"], body=[
                 ["Your order {n}{m}71 ({n} machined brackets, 6061-T6) shipped today.", "Expected delivery: {day}.",
                  "Inspection report is in the packing slip envelope."],
                 ["Order {n}{m}71 is delayed by one day because of a tooling change.", "New delivery date: {day2}.",
                  "Sorry for the inconvenience."]]),
             dict(by="B", p=0.6, body=[["Thanks, please send the inspection report by email as well."],
                                       ["Thanks for letting us know. {day2} is fine."]]),
             dict(by="A", p=0.5, body=[["Sent separately, thank you."], ["Noted, thank you."]]),
         ]),
    dict(id="it_help", weight=1.5, max=3, roles={"A": "hal", "B": "pid:p_frederik"},
         subject=["Monitor in 217 flickering", "Docking station not charging", "Projector in the 217 meeting room"],
         turns=[
             dict(by="A", to=["B"], body=[
                 ["The second monitor at my desk in 217 keeps flickering since this morning.",
                  "I tried another cable, same thing."],
                 ["My docking station stopped charging the laptop. Lights are on, but no power."],
                 ["The projector in the 217 meeting room shows no signal from the wall port."]]),
             dict(by="B", body=[
                 ["Logged as INC-22{n}{m}. Probably the panel. I will swap the monitor on my next visit.",
                  "Use the spare in the cupboard until then."],
                 ["Logged as INC-22{n}{m}. Please try the dock at the desk next to yours meanwhile.",
                  "I will bring a replacement on my next visit."],
                 ["Logged as INC-22{n}{m}. The wall port needs a reset, I will do it on my next visit.",
                  "The HDMI cable in the drawer works as a workaround."]]),
             dict(by="A", p=0.7, body=[["Thanks Frederik."], ["Thanks, using the spare for now."]]),
         ]),
    dict(id="expenses", weight=1, max=2, roles={"A": "hal", "B": "pid:p_bg_06"},
         subject=["Summit expenses", "Expense question"],
         turns=[
             dict(by="A", to=["B"], body=[
                 ["Can summit lunches be expensed or are they covered by the registration?"],
                 ["Quick question: which cost code do I use for the machine shop order?"]]),
             dict(by="B", body=[
                 ["Lunch is included in the registration, so no expenses for those please.",
                  "Dinners with partners need a note."],
                 ["Use the engineering materials code, it is in the finance sheet on the second tab."]]),
             dict(by="A", p=0.6, body=[["Got it, thanks."], ["Perfect, thanks Sofia."]]),
         ]),
    dict(id="summit_question", weight=1, max=2, days="to_0305",
         roles={"A": "hal", "B": "ext:" + SUMMIT[0] + "|" + SUMMIT[1]},
         subject=["Question about summit registration", "Summit session capacity"],
         turns=[
             dict(by="A", to=["B"], body=[
                 ["Can colleagues from our other office register with the floor member code?"],
                 ["Is there a capacity limit for the {talk} session? Several of us would like to attend."]]),
             dict(by="B", body=[
                 ["Thank you for your question. The member code covers people who work on the JRR second floor only.",
                  "Others can register as guests on the summit site."],
                 ["Thank you for your interest. The {talk} session has 120 seats, first come first served.",
                  "We recommend arriving ten minutes early."]]),
             dict(by="A", p=0.5, body=[["Thanks for the quick answer."], ["Great, thank you."]]),
         ]),
    dict(id="talk_recap", weight=2, max=5, days="summit", needs="past_talk", roles={"A": "hal", "B": "hal"},
         subject=["Notes from {past_talk}", "Summit recap: {past_talk}"],
         turns=[
             dict(by="A", to=["list:" + L_ALL], body=[
                 ["Short notes from {past_talk} for those who missed it:",
                  "- the speakers showed a test lab that reruns every failed case automatically overnight",
                  "- two open-source tools worth a look for our {topic}",
                  "- slides should be on the summit site by tonight"],
                 ["Three takeaways from {past_talk}:", "- start with the data you already log",
                  "- write the safety argument before the model, not after",
                  "- small teams get most value from automating test reports"]]),
             dict(by="B", p=0.8, body=[
                 ["Thanks, the overnight rerun idea would help with the {topic}."],
                 ["Thanks for writing this up, very useful."]]),
             dict(by="A", p=0.3, body=[["Happy to show the demo video at standup."], ["Glad it helps."]]),
         ]),
    dict(id="doc_review", weight=3, roles={"A": "eng", "B": "eng"},
         subject=["Review request: {topic} draft", "Comments on the {topic}?"],
         turns=[
             dict(by="A", to=["B"], body=[
                 ["Could you review the {topic} draft by {day}? It is in the team folder, about {n} pages.",
                  "Mostly interested in whether the assumptions section holds up."],
                 ["I updated the {topic} after the last review. Do you have time to look at the changes before {day}?",
                  "Changes are highlighted in yellow."]]),
             dict(by="B", body=[
                 ["Yes, I will send comments by {day} morning."], ["Sure, I will go through the highlighted parts tomorrow."]]),
             dict(by="B", p=0.6, body=[
                 ["Comments are in the doc. Main one: the load assumptions need a reference."],
                 ["Done, only small comments. Looks good to me."]]),
             dict(by="A", p=0.6, body=[["Thanks, fixing the references now."], ["Great, thanks for the quick turnaround."]]),
         ]),
]
