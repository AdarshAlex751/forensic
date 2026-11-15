"""Case 1010F generator: builds the raw case folder, the expected events and the answer key from CASE.md.

Pipeline (build.py): world -> presence simulation -> story overlay -> other sources -> writers -> tamper ->
manifest -> answer key -> validate. Every writer reports the exact line and text it wrote, so nothing is
numbered or quoted by hand.
"""
