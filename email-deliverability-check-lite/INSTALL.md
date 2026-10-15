# Install Email Deliverability Check Lite

Requires Python 3.9 or newer. No other installs.

## Claude Code

Copy this folder so the path is `~/.claude/skills/email-deliverability-check-lite/SKILL.md` (or `.claude/skills/` inside a project), start a new session and ask, for example:

> My emails from example.com go to spam. Check it.

## Codex

Copy to `~/.codex/skills/email-deliverability-check-lite/` and start a new session.

## Without an agent

```sh
python3 scripts/check_email.py your-domain.com --output report.md --json report.json
python3 scripts/check_email.py example.com --records examples/clean-records.json
python3 scripts/check_email.py example.org --records examples/broken-records.json
python3 -m unittest discover -s tests -v
```

`--resolver IP` picks the DNS server (default: first `nameserver` in `/etc/resolv.conf`; on Windows always pass it). `--records FILE` reads `"name TYPE": [values]` from JSON instead of DNS. `--org-domain` sets the organisational domain for two-label suffixes such as `co.uk`.

## Limits

Not checked: DKIM, SPF lookups through includes, received messages, IP or domain reputation, blocklists, spam rate, reverse DNS, TLS, content. A clean report means the checked records are correct, not that every message reaches the inbox.
