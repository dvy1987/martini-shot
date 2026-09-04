"""Shots and alternates (AL-1).

Every generated clip is an ALTERNATE attached to its shot — never a silent
overwrite (A5). A shot can be LOCKED; the approval executor refuses any
command targeting a locked shot at dispatch time, centrally, for every
caller (H-0 design, Locked-target guard). add/remove-from-continuity are
approval-tracked actions through H-0's default_registry — there is no second
action path.

Collections: `pc-shots`, `pc-alternates` (Firestore, canonical state).
"""
