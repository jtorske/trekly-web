"""Trekly Guide: the deterministic trail assistant.

Everything here is plain code over Trekly's own data: no AI, no paid
services. The pieces are pure functions over plain values so they can be
called from the HTTP endpoints (app/routers/guide.py), from the persona
evals (tests/guide/), and later from an AI chat layer that only calls them.

- estimate.py: trail times (Naismith), seasons, scenery labels
- profile.py: get_hiker_profile / build_profile, what Trekly knows about a hiker
- recommend.py: recommend(profile, request, trails), ranked trails with reasons
- readiness.py: readiness(profile, trail, date), "Am I ready?"
"""
