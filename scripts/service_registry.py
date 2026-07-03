"""Service registry — the single source of truth for "what is an AM / PM / Wednesday service."

The point: a raw `POST /plans` makes only a bare shell. The web UI silently applies a
template (its items, needed positions, and people) — a Category-A cascade. This registry
makes that template the *unmarked default*: every recurring service resolves by a short
handle to its service type, its master template, and its default time. Booking from here
(see book_service.py) is never blank; only deviations from the template get mentioned.

To add a service: add a row. To re-point a template (e.g. a new Wednesday master), edit one
line here instead of hunting hard-coded IDs across your task scripts.

Times are your normal start times; they're best-guess defaults — adjust as needed, they're
only the plan_time seed. Weekday uses Python's Monday=0 .. Sunday=6.

FILL IN YOUR OWN IDs — the entries below are EXAMPLES with placeholder IDs:
  * service_type_id — open the service type in the PCO web UI; the ID is in the URL
    (https://services.planningcenteronline.com/service_types/<ID>/...).
  * template_id — list templates via the API:
    GET /services/v2/service_types/<ID>/plan_templates
    (or open the template in the web UI and read the ID from the URL).
"""
from __future__ import annotations

# handle -> service definition
SERVICES: dict[str, dict] = {
    "sunday_am": {
        "service_type_id": "1111111",    # your service type ID here
        "service_type_name": "Sunday AM",
        "template_id": "2222222",        # your template ID here
        "template_name": "Sunday AM Template",
        "weekday": 6,            # Sunday
        "time": "10:45",         # local (your service-type timezone)
        "duration_min": 75,
        "time_type": "service",  # MUST be "service": PCO only derives a plan's headline date
                                 # from service-type times. A "rehearsal" time => plan shows
                                 # "No dates" even though a time exists.
    },
    "wed_night": {
        "service_type_id": "3333333",    # your service type ID here
        "service_type_name": "Wednesday Night",
        "template_id": "4444444",        # your template ID here
        "template_name": "Wednesday Night Template",
        "weekday": 2,            # Wednesday
        "time": "19:00",
        "duration_min": 90,
        "time_type": "service",
    },
}

# Friendly aliases people might type instead of the canonical handle.
ALIASES: dict[str, str] = {
    "am": "sunday_am",
    "sun_am": "sunday_am",
    "morning": "sunday_am",
    "wednesday": "wed_night",
    "wed": "wed_night",
    "evening": "wed_night",
}


def resolve(handle: str) -> tuple[str, dict]:
    """Return (canonical_handle, service_def). Accepts aliases. Raises KeyError with a
    helpful message on an unknown handle."""
    key = (handle or "").strip().lower().replace("-", "_").replace(" ", "_")
    key = ALIASES.get(key, key)
    if key not in SERVICES:
        known = ", ".join(sorted(SERVICES) + sorted(ALIASES))
        raise KeyError(f"unknown service handle {handle!r}. known: {known}")
    return key, SERVICES[key]


def by_service_type(st_id: str) -> tuple[str, dict] | None:
    """Reverse lookup: which registered service owns this service-type id."""
    st_id = str(st_id)
    for handle, svc in SERVICES.items():
        if svc["service_type_id"] == st_id:
            return handle, svc
    return None


def handles() -> list[str]:
    return list(SERVICES)


if __name__ == "__main__":
    print("Registered services:")
    for h, s in SERVICES.items():
        print(f"  {h:12} st={s['service_type_id']:>8}  tpl={s['template_id']:>8}  "
              f"{s['time']} (wd{s['weekday']})  {s['service_type_name']}")
