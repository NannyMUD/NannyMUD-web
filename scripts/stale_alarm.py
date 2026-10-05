"""Mail when the mud's export goes stale, and again when it recovers.

Run after each fetch (docker/builder.sh). Every export file carries the
time the mud wrote it ("generated"). When the oldest is more than
NANNY_STALE_HOURS (30) old, mail NANNY_ALERT_TO, at most once a day while
it stays stale; mail once more when it is fresh again. What was last sent
is kept in alarm.json next to the data, so a restart does not mail twice.

Mail goes through NANNY_SMTP_HOST (the wiki's SES SMTP on the box) with
NANNY_SMTP_USER and NANNY_SMTP_PASS. Without NANNY_SMTP_HOST or
NANNY_ALERT_TO it only writes to the log. Python's standard library only.
"""
import json
import os
import smtplib
import sys
import time
from email.message import EmailMessage

DATA = os.environ.get("NANNY_DATA_DIR", "data")
STATE = os.path.join(DATA, "alarm.json")
FILES = ("quests", "puzzles", "staff", "areas", "guilds", "help", "stats")
DAY = 24 * 3600


def export_times():
    """{name: generated} for every export file that has one."""
    times = {}
    for name in FILES:
        try:
            with open(os.path.join(DATA, name + ".json"), encoding="utf-8") as fh:
                generated = json.load(fh).get("generated")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(generated, (int, float)) and generated > 0:
            times[name] = int(generated)
    return times


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE + ".new"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE)


def send(subject, body):
    """Mail it; True when it went (or there is nowhere to send it)."""
    host = os.environ.get("NANNY_SMTP_HOST", "")
    to = os.environ.get("NANNY_ALERT_TO", "")
    print("alarm: " + subject)
    if not host or not to:
        print("alarm: NANNY_SMTP_HOST or NANNY_ALERT_TO not set, not mailed")
        return True
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("NANNY_ALERT_FROM", "nannymud-web@localhost")
    msg["To"] = to
    msg.set_content(body)
    port = int(os.environ.get("NANNY_SMTP_PORT", "587"))
    tls = os.environ.get("NANNY_SMTP_TLS", "starttls")  # starttls, ssl or none
    try:
        if tls == "ssl":
            smtp = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
        with smtp:
            if tls == "starttls":
                smtp.starttls()
            user = os.environ.get("NANNY_SMTP_USER", "")
            if user:
                smtp.login(user, os.environ.get("NANNY_SMTP_PASS", ""))
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        print("alarm: mail failed: %s" % e)
        return False
    return True


def main():
    now = int(time.time())
    limit = float(os.environ.get("NANNY_STALE_HOURS", "30")) * 3600
    site = os.environ.get("NANNY_SITE_URL", "the website")
    times = export_times()
    state = load_state()
    stale = {n: t for n, t in times.items() if now - t > limit}
    if not times:
        stale = {"(no export files)": 0}

    if stale:
        if now - state.get("mailed", 0) < DAY - 600:
            print("alarm: export still stale, mailed already today")
            return 0
        oldest = min(stale.values())
        lines = ["%-8s written %s" % (n, time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
                                       if t else "never")
                 for n, t in sorted(stale.items())]
        body = ("The mud's export behind %s has not been refreshed for more than "
                "%g hours.\n\n%s\n\nThe site is still built from the last data it "
                "has. This mail repeats once a day until the export is fresh again.\n"
                % (site, limit / 3600, "\n".join(lines)))
        subject = "NannyMUD website: export stale since %s" % (
            time.strftime("%Y-%m-%d %H:%M", time.localtime(oldest)) if oldest else "unknown")
        if send(subject, body):
            state.update(stale_since=state.get("stale_since") or oldest or now, mailed=now)
            save_state(state)
        return 0

    if state.get("stale_since"):
        body = ("The mud's export behind %s is fresh again (newest data from %s).\n"
                % (site, time.strftime("%Y-%m-%d %H:%M", time.localtime(min(times.values())))))
        if send("NannyMUD website: export fresh again", body):
            save_state({})
    return 0


if __name__ == "__main__":
    sys.exit(main())
