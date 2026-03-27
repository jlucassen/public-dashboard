"""Email notifications via Gmail SMTP."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_alert(
    sender_email: str,
    app_password: str,
    recipients: list[str],
    bad_days: list[tuple[str, int, list[str]]],
):
    """Send alert email about consecutive bad days.

    bad_days: list of (date_str, red_count, red_metric_names) tuples.
    """
    assert recipients, "No recipients provided"
    assert bad_days, "No bad days provided"

    n = len(bad_days)
    subject = f"Dashboard Alert: {n} consecutive rough days"

    lines = [
        "Hey,",
        "",
        f"James has been in the red on 5+ metrics for {n} days in a row.",
        "Here's the breakdown:",
        "",
    ]

    for date_str, count, metrics in bad_days:
        lines.append(f"  {date_str} — {count} red metrics:")
        for m in metrics:
            label = f"{m} (x2)" if m == "Work" else m
            lines.append(f"    - {label}")
        lines.append("")

    lines.append("Maybe check in on him?")
    lines.append("")
    lines.append("-Claude Opus 4.6")

    body = "\n".join(lines)

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, recipients, msg.as_string())

    print(f"  Alert email sent to {len(recipients)} recipient(s)")
