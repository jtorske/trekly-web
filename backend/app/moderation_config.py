"""Every moderation threshold in one place (read by app/moderation.py).

Change a number here and it applies everywhere: screening, reports, the
new-account limits and the admin digest. Nothing else in the app hard-codes
these.
"""

from datetime import timedelta

# ------------------------------------------------------------------ screening
# OpenAI's moderation endpoint (text and images in one request). The key is
# OPENAI_API_KEY in the environment; without one, screening counts as down.
MODERATION_MODEL = "omni-moderation-latest"
MODERATION_URL = "https://api.openai.com/v1/moderations"
# A slow answer counts as down: the content publishes and waits for review.
MODERATION_TIMEOUT_SECONDS = 6.0

# Content is held when OpenAI flags it, or when any category's score reaches
# the number given here (stricter than OpenAI's own line). Empty: OpenAI's
# `flagged` decides alone.
CATEGORY_HOLD_SCORES: dict[str, float] = {}

# A flag in any of these starts the child-safety flow: hidden at once, kept,
# the account locked, and an urgent email (app/moderation.py).
CHILD_SAFETY_CATEGORIES = ("sexual/minors",)

# ------------------------------------------------------------------ reports
# Distinct reporters on open reports that hide an item pending review.
REPORTS_TO_HIDE = 3
# A report counts toward that only from an account this old, with a confirmed email.
REPORTER_MIN_ACCOUNT_AGE = timedelta(days=7)
# Each account's reports, in a rolling day (one per profile a day, too).
REPORTS_PER_DAY = 5

# ------------------------------------------------------------------ new accounts
# "New" for the rate limits below: the first day after sign-up.
NEW_ACCOUNT_PERIOD = timedelta(hours=24)

# (count, window): at most `count` new ones in any `window`. A post is a new
# Trail Journal entry (the "Log a hike" composer, a trail's dialog).
POST_LIMITS = ((30, timedelta(hours=1)), (100, timedelta(days=1)))
NEW_ACCOUNT_POST_LIMITS = ((5, timedelta(hours=1)), (15, timedelta(days=1)))
COMMENT_LIMITS = ((30, timedelta(hours=1)), (200, timedelta(days=1)))
NEW_ACCOUNT_COMMENT_LIMITS = ((5, timedelta(hours=1)), (20, timedelta(days=1)))

# Photos (hike photos, profile photos) and comments wait for a confirmed email.
PHOTOS_NEED_CONFIRMED_EMAIL = True
COMMENTS_NEED_CONFIRMED_EMAIL = True

# ------------------------------------------------------------------ notifications
# At most one "held and reported" digest email to the admin in this long.
DIGEST_INTERVAL = timedelta(hours=1)
# Where admin emails go (PROFILE_REPORTS_EMAIL overrides it, as before), and
# the appeal address in emails to authors.
ADMIN_EMAIL = "treklyusersupport@gmail.com"
APPEAL_EMAIL = "treklyusersupport@gmail.com"
# Items listed in one digest; the rest are counted, with a link to the queue.
DIGEST_MAX_ITEMS = 25

# ------------------------------------------------------------------ admin actions
MAX_SUSPENSION_DAYS = 365
