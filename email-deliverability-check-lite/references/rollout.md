# Moving DMARC from monitoring to enforcement

Each step changes only the `_dmarc.<domain>` TXT record. Move on only when the aggregate reports for the previous step show every service you use passing DMARC (SPF or DKIM aligned). Reports arrive daily from Google, Yahoo, Microsoft and others at the `rua` address; a DMARC report service turns the XML into a readable list.

1. **Monitor** for at least 2 weeks: `v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com`
   Find every source sending as your domain. Fix each legitimate one (custom DKIM, custom return-path) or stop it.
2. **Quarantine a quarter**: `v=DMARC1; p=quarantine; pct=25; rua=mailto:dmarc-reports@example.com`
   1–2 weeks. Failing mail goes to spam at a quarter of receivers' discretion.
3. **Quarantine all**: `v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@example.com`
4. **Reject** after another 2–4 clean weeks: `v=DMARC1; p=reject; rua=mailto:dmarc-reports@example.com`

If a step shows your own mail failing, go back one step, fix the source, and wait again. Subdomains follow `sp=` (or `p=` when sp is absent). Domains that never send mail can go straight to `v=DMARC1; p=reject` with SPF `v=spf1 -all`.
