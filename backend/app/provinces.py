"""Canada's 13 provinces and territories, for a profile's home province.

Stored as the two-letter postal code; None means "Prefer not to say". The
frontend has the names, colours and badge art (lib/provinces.ts); a test
checks both lists match.
"""

from typing import Literal

PROVINCE_CODES = ("AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT")

ProvinceCode = Literal["AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"]

# The featured-badge id for "my home province" (stored in featured_badges.milestone,
# which no milestone uses: app/milestones_config.py ids are checked against it).
PROVINCE_BADGE = "home-province"
