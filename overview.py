"""Deterministic weekly aggregation and per-subject grade histories."""

from datetime import date, datetime, timedelta
import json
from statistics import mean

from communication import CHILD, tool
import pedagogy


TOOLS = [
    tool("summarize_week", "Return a weekly data overview, not an AI-written summary. Includes timetable, homework due that week, lesson contents, and overlapping absences and delays. Keeps canceled/replacement lessons intact. Does not infer closures from announcements. Each section can report its own failure.", {
        "date": {"type": "string", "description": "Any YYYY-MM-DD date in the requested week. Defaults to today."},
        "child_name": CHILD,
    }),
    tool("get_grade_trend", "Return per-subject chronological grade histories and arithmetic summaries across selected periods. Defaults to the current period. Values on 20 are normalized scores, not official averages. Duplicate grades appearing in several periods are excluded from the overall history.", {
        "period_names": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 12, "uniqueItems": True},
        "subject": {"type": "string", "description": "Optional exact subject name, case-insensitive."},
        "child_name": CHILD,
    }),
]


async def handle(name, client, args, child, handlers, find_period, format_grade, format_absence, format_delay):
    if name == "summarize_week":
        day = datetime.strptime(args["date"], "%Y-%m-%d").date() if args.get("date") else date.today()
        start = day - timedelta(days=day.weekday())
        end = start + timedelta(days=6)
        sections = {}
        errors = {}
        for section, handler, options in (
            ("timetable", handlers["timetable"], {"date": start.isoformat(), "date_to": end.isoformat()}),
            ("homework", handlers["homework"], {"date_from": start.isoformat(), "date_to": end.isoformat()}),
        ):
            try:
                sections[section] = json.loads((await handler(client, options, child))[0].text)
            except Exception:
                sections[section] = None
                errors[section] = {"error_code": "SECTION_UNAVAILABLE", "error": "The weekly section could not be read."}
        try:
            options = {"date_from": start.isoformat(), "date_to": end.isoformat(), "limit": 200}
            rows = []
            while True:
                page = pedagogy.handle("get_lesson_contents", client, options, child)
                rows.extend(page["lesson_contents"])
                if page["next_offset"] is None:
                    break
                options["offset"] = page["next_offset"]
            sections["lesson_contents"] = rows
        except Exception:
            sections["lesson_contents"] = None
            errors["lesson_contents"] = {"error_code": "SECTION_UNAVAILABLE", "error": "Lesson contents could not be read."}
        try:
            periods = [period for period in client.periods if as_date(period.start) <= end and as_date(period.end) >= start]
            absences, delays = [], []
            for period in periods:
                absences.extend(format_absence(row) for row in period.absences if as_date(row.from_date) <= end and as_date(row.to_date) >= start)
                delays.extend(format_delay(row) for row in period.delays if start <= as_date(row.date) <= end)
            # Period groups can overlap. Return each identical entry only once.
            sections["attendance"] = {"absences": list({json.dumps(row, sort_keys=True): row for row in absences}.values()),
                                      "delays": list({json.dumps(row, sort_keys=True): row for row in delays}.values())}
        except Exception:
            sections["attendance"] = None
            errors["attendance"] = {"error_code": "SECTION_UNAVAILABLE", "error": "Attendance could not be read."}
        return {"child": child, "date_from": start.isoformat(), "date_to": end.isoformat(),
                "sections": sections, "partial": bool(errors), "section_errors": errors,
                "note": "Announcements may contradict the timetable. Canceled and replacement entries are not merged."}
    if name != "get_grade_trend":
        raise ValueError("Unknown overview tool.")
    names = args.get("period_names")
    periods = [find_period(client, item) for item in names] if names else [client.current_period]
    groups = {}
    seen = set()
    for period in periods:
        for row in period.grades:
            subject = row.subject.name if row.subject else "Unknown subject"
            if args.get("subject") and subject.casefold() != args["subject"].casefold():
                continue
            data = format_grade(row)
            identifier = getattr(row, "id", None)
            key = (subject, identifier) if isinstance(identifier, str) and identifier else (subject, data["date"], data["grade"], data["out_of"], data["comment"], data["coefficient"])
            if key in seen:
                continue
            seen.add(key)
            data["period"] = period.name
            groups.setdefault(subject, []).append(data)
    result = []
    for subject, rows in sorted(groups.items()):
        rows.sort(key=lambda row: row["date"] or "")
        comparable = [row["grade_on_20"] for row in rows if row["grade_on_20"] is not None]
        result.append({"subject": subject, "grades": rows, "grade_count": len(rows), "numeric_grade_count": len(comparable),
                       "mean_on_20": round(mean(comparable), 6) if comparable else None,
                       "first_on_20": comparable[0] if comparable else None,
                       "latest_on_20": comparable[-1] if comparable else None,
                       "change_on_20": round(comparable[-1] - comparable[0], 6) if len(comparable) > 1 else None})
    return {"child": child, "periods": [period.name for period in periods], "subjects": result,
            "note": "Means are unweighted descriptive values, not official averages. Bonus and optional grades remain in the history."}


def as_date(value):
    return value.date() if isinstance(value, datetime) else value
