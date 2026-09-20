from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone


FUNNELS = [
    {
        "key": "listing_creation",
        "label": "Create and publish a listing",
        "steps": [
            ("listing_started", "Started"),
            ("listing_photos_added", "Added photos"),
            ("listing_created", "Created"),
            ("listing_published", "Published"),
        ],
    },
    {
        "key": "trade_offer",
        "label": "Send a trade offer",
        "steps": [
            ("marketplace_listing_viewed", "Viewed listing"),
            ("trade_composer_started", "Started offer"),
            ("trade_offer_submitted", "Sent offer"),
        ],
    },
    {
        "key": "profile_completion",
        "label": "Complete profile",
        "steps": [
            ("profile_started", "Started"),
            ("profile_saved", "Saved"),
        ],
    },
]

ERROR_EVENTS = {"ui_error", "listing_photo_check_failed", "listing_analysis_failed"}


def build_experience_report(events: list[dict], *, days: int, minimum_sample: int = 5) -> dict:
    sessions: set[str] = set()
    users: set[str] = set()
    error_counts: Counter[tuple[str, str, str]] = Counter()
    error_users: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    user_sequences: dict[str, list[str]] = defaultdict(list)

    for event in events:
        name = str(event.get("event_name") or "")
        owner = str(event.get("owner_subject") or "")
        session = str(event.get("session_id") or "")
        if owner:
            users.add(owner)
            user_sequences[owner].append(name)
        if session:
            sessions.add(session)
        if name in ERROR_EVENTS:
            properties = event.get("properties") if isinstance(event.get("properties"), dict) else {}
            key = (
                name,
                str(event.get("screen") or "unknown"),
                str(properties.get("error_code") or properties.get("reason") or "unspecified")[:120],
            )
            error_counts[key] += 1
            if owner:
                error_users[key].add(owner)

    funnels = []
    findings = []
    for definition in FUNNELS:
        steps = []
        previous_count = None
        largest_loss = None
        progressed_users = set(users)
        previous_positions: dict[str, int] = {owner: -1 for owner in users}
        for event_name, label in definition["steps"]:
            next_progressed: set[str] = set()
            next_positions: dict[str, int] = {}
            for owner in progressed_users:
                sequence = user_sequences[owner]
                start_at = previous_positions.get(owner, -1) + 1
                try:
                    position = sequence.index(event_name, start_at)
                except ValueError:
                    continue
                next_progressed.add(owner)
                next_positions[owner] = position
            progressed_users = next_progressed
            previous_positions = next_positions
            count = len(progressed_users)
            conversion = None if previous_count in (None, 0) else round((count / previous_count) * 100, 1)
            loss = None if previous_count is None else max(previous_count - count, 0)
            steps.append({
                "event_name": event_name,
                "label": label,
                "users": count,
                "conversion_from_previous_pct": conversion,
                "drop_off_users": loss,
            })
            if previous_count is not None and previous_count >= minimum_sample:
                candidate = {"from": steps[-2]["label"], "to": label, "users": loss, "rate": round((loss / previous_count) * 100, 1)}
                if largest_loss is None or candidate["rate"] > largest_loss["rate"]:
                    largest_loss = candidate
            previous_count = count
        funnels.append({"key": definition["key"], "label": definition["label"], "steps": steps, "largest_drop_off": largest_loss})
        if largest_loss and largest_loss["rate"] >= 20:
            findings.append({
                "severity": "high" if largest_loss["rate"] >= 50 else "medium",
                "category": "drop_off",
                "title": f"{definition['label']}: {largest_loss['rate']}% drop-off",
                "evidence": f"{largest_loss['users']} users did not progress from {largest_loss['from']} to {largest_loss['to']}.",
                "recommendation": f"Review the transition from {largest_loss['from']} to {largest_loss['to']} and test it with affected users.",
            })

    friction = []
    for key, count in error_counts.most_common(10):
        event_name, screen, reason = key
        affected = len(error_users[key])
        item = {"event_name": event_name, "screen": screen, "reason": reason, "occurrences": count, "affected_users": affected}
        friction.append(item)
        if affected >= minimum_sample or count >= minimum_sample * 2:
            findings.append({
                "severity": "high" if affected >= minimum_sample * 2 else "medium",
                "category": "friction",
                "title": f"Repeated problem on {screen}",
                "evidence": f"{count} occurrences affected {affected} users. Signal: {reason}.",
                "recommendation": "Reproduce this path, inspect correlated API errors, and validate the fix with event-rate monitoring.",
            })

    findings.sort(key=lambda item: (item["severity"] != "high", item["category"], item["title"]))
    next_steps = []
    for index, finding in enumerate(findings[:5], start=1):
        if finding["category"] == "drop_off":
            success_metric = "Increase progression through this funnel transition by at least 10 percentage points."
        else:
            success_metric = "Reduce occurrences and affected users by at least 50% in the next reporting window."
        next_steps.append({
            "priority": index,
            "title": finding["title"],
            "action": finding["recommendation"],
            "success_metric": success_metric,
        })

    data_quality = "sufficient" if len(users) >= minimum_sample else "insufficient"
    if data_quality == "insufficient":
        executive_summary = (
            f"Telemetry is collecting data, but only {len(users)} users are represented. "
            f"At least {minimum_sample} are required before reporting drop-off patterns."
        )
    elif findings:
        high_count = sum(1 for finding in findings if finding["severity"] == "high")
        executive_summary = (
            f"The agent identified {len(findings)} actionable pattern{'s' if len(findings) != 1 else ''}, "
            f"including {high_count} high-priority issue{'s' if high_count != 1 else ''}."
        )
    else:
        executive_summary = "No statistically meaningful drop-off or repeated-friction pattern was detected in this reporting window."
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "minimum_sample": minimum_sample,
        "sample": {"events": len(events), "users": len(users), "sessions": len(sessions)},
        "data_quality": data_quality,
        "executive_summary": executive_summary,
        "funnels": funnels,
        "friction_signals": friction,
        "findings": findings,
        "next_steps": next_steps,
        "methodology": "Users count only when they complete funnel events in sequence. Findings require the configured minimum sample and at least 20% transition drop-off or repeated failures.",
    }
