from __future__ import annotations

import json
import os
import smtplib
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage


def _send_email_alert(subject: str, body: str) -> None:
    smtp_host = (os.environ.get("HEALTH_ALERT_SMTP_HOST") or "").strip()
    smtp_username = (os.environ.get("HEALTH_ALERT_SMTP_USERNAME") or "").strip()
    smtp_password = (os.environ.get("HEALTH_ALERT_SMTP_PASSWORD") or "").strip()
    smtp_port = int(os.environ.get("HEALTH_ALERT_SMTP_PORT") or "587")
    email_from = (os.environ.get("HEALTH_ALERT_EMAIL_FROM") or "admin@jouft.com").strip()
    email_to = (os.environ.get("HEALTH_ALERT_EMAIL_TO") or "leavethemessage@gmail.com").strip()
    if not smtp_host or not smtp_username or not smtp_password:
        print("email alert skipped: SMTP health alert secrets are not configured")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = email_from
    message["To"] = email_to
    message.set_content(body)
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
        print(f"email alert sent to {email_to}")
    except Exception as exc:
        print(f"email alert failed: {exc}")


def _post_alert(message: str) -> None:
    webhook_url = (os.environ.get("HEALTH_ALERT_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return
    payload = json.dumps({"text": message}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print(f"alert webhook HTTP {response.status}")
    except Exception as exc:
        print(f"alert webhook failed: {exc}")


def _send_alert(subject: str, body: str) -> None:
    _post_alert(body)
    _send_email_alert(subject, body)


def _request_json(url: str, api_key: str | None = None) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body or "{}")
        except json.JSONDecodeError:
            parsed = {"detail": body[:300]}
        return exc.code, parsed


def _print_dependency_report(body: dict) -> None:
    checks = body.get("checks") or []
    if not isinstance(checks, list):
        return
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = check.get("name")
        status = check.get("status")
        latency = check.get("latency_ms")
        message = check.get("message")
        line = f"{name}: {status}"
        if latency is not None:
            line += f" ({latency} ms)"
        if message:
            line += f" - {message}"
        print(line)


def _dependency_summary(body: dict) -> str:
    checks = body.get("checks") or []
    if not isinstance(checks, list):
        return "Dependency response did not include checks."
    failing = [
        check
        for check in checks
        if isinstance(check, dict) and check.get("status") in {"degraded", "down"}
    ]
    if not failing:
        return "No failing dependency details were returned."
    parts = []
    for check in failing[:8]:
        name = check.get("name") or "unknown"
        status = check.get("status") or "unknown"
        message = check.get("message")
        detail = f"{name}={status}"
        if message:
            detail += f" ({message})"
        parts.append(detail)
    return "; ".join(parts)


def main() -> int:
    if os.environ.get("SEND_TEST_HEALTH_ALERT_EMAIL", "false").lower() == "true":
        _send_email_alert(
            "JOUFT health alert email test",
            (
                "This is a test email from the JOUFT production health monitor.\n\n"
                "If you received this, SMTP alert delivery is configured correctly."
            ),
        )
        return 0

    base_url = os.environ.get("PROD_HEALTH_URL", "https://api.jouft.com").rstrip("/")
    api_key = (os.environ.get("PROD_HEALTH_API_KEY") or "").strip()
    require_dependency_health = (
        os.environ.get("REQUIRE_DEPENDENCY_HEALTH", "false").lower() == "true"
    )

    status_code, health = _request_json(f"{base_url}/v1/health")
    print(f"application health HTTP {status_code}: {health}")
    if status_code >= 400 or health.get("status") != "ok":
        _send_alert(
            "JOUFT production application health failed",
            (
                "JOUFT production application health failed.\n\n"
                f"URL: {base_url}/v1/health\n"
                f"HTTP status: {status_code}\n"
                f"Response: {health}"
            ),
        )
        return 1

    if not api_key:
        print("dependency health skipped: PROD_HEALTH_API_KEY is not configured")
        if require_dependency_health:
            _send_alert(
                "JOUFT dependency health check is not configured",
                "JOUFT dependency health failed because PROD_HEALTH_API_KEY is missing.",
            )
            return 1
        return 0

    status_code, dependencies = _request_json(f"{base_url}/v1/health/dependencies", api_key=api_key)
    print(f"dependency health HTTP {status_code}: status={dependencies.get('status')}")
    _print_dependency_report(dependencies)
    if status_code >= 400 or dependencies.get("status") != "ok":
        _send_alert(
            "JOUFT production dependency health failed",
            (
                "JOUFT production dependency health failed.\n\n"
                f"URL: {base_url}/v1/health/dependencies\n"
                f"HTTP status: {status_code}\n"
                f"Overall status: {dependencies.get('status')}\n"
                f"Failing checks: {_dependency_summary(dependencies)}"
            ),
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
