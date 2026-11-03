"""The day each milestone was first earned (app/milestone_dates.py)."""

from datetime import date

from app.milestone_dates import earned_dates
from app.milestones import Facts, Hike, evaluate
from app.milestones_config import BY_ID, CORE_SLOT_CATEGORIES
from tests.test_featured_badges import alice, hike, people, trails  # noqa: F401  (fixtures)
from tests.test_milestones import trail

D = date.fromisoformat


def dates(facts: Facts, ids: list[str], plans=(), alerts=(), notified=()) -> dict[str, date]:
    results = evaluate(facts, [BY_ID[i] for i in ids])
    return earned_dates(facts, results, plan_dates=list(plans), alert_dates=list(alerts), notified_dates=list(notified))


def test_a_count_is_earned_on_the_hike_that_reaches_it():
    hikes = [Hike(trail(), D(f"2026-0{m}-01")) for m in (7, 5, 6)]
    assert dates(Facts(hikes=hikes), ["first-hike"]) == {"first-hike": D("2026-05-01")}


def test_an_undated_hike_counts_from_the_day_it_was_logged():
    hikes = [Hike(trail(), None, logged_on=D("2026-04-02")), Hike(trail(), D("2026-08-01"))]
    assert dates(Facts(hikes=hikes), ["first-hike"]) == {"first-hike": D("2026-04-02")}


def test_unearned_milestones_have_no_date():
    assert dates(Facts(hikes=[Hike(trail(), D("2026-05-01"))]), ["trail-regular"]) == {}


def test_plans_and_alerts_by_the_day_they_were_made():
    got = dates(
        Facts(plans=1, alerts=2, alert_notified=True),
        ["planner", "permit-hunter", "lucky-break"],
        plans=[D("2026-03-03")],
        alerts=[D("2026-03-09"), D("2026-02-01")],
        notified=[D("2026-03-20")],
    )
    assert got == {"planner": D("2026-03-03"), "permit-hunter": D("2026-02-01"), "lucky-break": D("2026-03-20")}


def test_a_setup_counts_from_its_last_change():
    full = {categories[0] for categories in CORE_SLOT_CATEGORIES.values()}
    partial = set(list(full)[:2])
    facts = Facts(setups=[partial, full], setup_dates=[D("2026-01-05"), D("2026-02-10")])
    assert dates(facts, ["packed-and-ready"]) == {"packed-and-ready": D("2026-02-10")}


def test_the_api_sends_the_day_earned(client, alice):  # noqa: F811
    by_id = {m["id"]: m for m in client.get("/api/me/milestones", headers=alice).json()["milestones"] if m["id"]}
    # Alice's first hike was Lake Agnes on 2026-06-10.
    assert by_id["first-hike"]["earned_on"] == "2026-06-10"
    assert by_id["trail-regular"]["earned_on"] is None
