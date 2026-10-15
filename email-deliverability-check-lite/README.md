# Email Deliverability Check Lite

Find out why your email goes to spam, from your domain's DNS records. Works as a skill for Claude Code and Codex, or as a plain Python script.

- **Real DNS, no account.** Reads MX, SPF and DMARC straight from DNS. Python standard library only; no API key, signup or paid service.
- **Blocking problems first.** Two SPF records, `+all`, a DMARC record receivers ignore, an MX host that does not resolve. Every finding shows the record it came from.
- **Safe advice.** A step-by-step plan for moving DMARC from monitoring to enforcement without blocking your own mail.

## Quick start

As a skill: copy this folder to `~/.claude/skills/` (Claude Code) or `~/.codex/skills/` (Codex), start a new session and ask: "My emails from example.com go to spam. Check it." See [INSTALL.md](INSTALL.md).

Without an agent:

```bash
python3 scripts/check_email.py your-domain.com
python3 scripts/check_email.py example.org --records examples/broken-records.json   # offline example
```

## Lite and the full version

| | Lite (this repo, MIT) | [Email Deliverability Check](https://ohayo.si/skills/email-deliverability-check/) ($4.90) |
| --- | --- | --- |
| MX, SPF record and policy, DMARC record and policy | ✓ | ✓ |
| SPF lookup count (the 10-lookup limit) through every include | | ✓ |
| DKIM keys: present, valid, key size, testing flag | | ✓ |
| Received message: SPF/DKIM/DMARC results, alignment, one-click unsubscribe | | ✓ |
| DMARC report address authorisation | | ✓ |
| Records to publish: merged SPF with lookup count, next DMARC step | | ✓ |
| Provider checks for Google Workspace, Microsoft 365, SendGrid, Mailgun, Amazon SES, Zoho | | ✓ |

## License

MIT. See [LICENSE](LICENSE).
