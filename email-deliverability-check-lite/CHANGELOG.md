# Changelog

## 1.0.0 — 2026-10-15

- MX, SPF and DMARC checks from live DNS, with the record behind every finding.
- SPF: one record, syntax, `+all`/`?all`/missing `all`, deprecated `ptr`.
- DMARC: present, starts with v=DMARC1, valid tags, policy, percentage, report address; subdomains inherit the organisational record.
- Offline examples and a DMARC rollout plan.
