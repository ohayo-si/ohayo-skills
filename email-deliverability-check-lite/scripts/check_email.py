"""Check a sending domain's MX, SPF, DKIM and DMARC records and, optionally, a received
message's authentication results. Standard library only; the only network traffic is
DNS queries to one resolver, capped per run."""
from __future__ import annotations

import argparse
import base64
import email
import email.policy
import email.utils
import ipaddress
import json
import os
import random
import re
import socket
import struct
import sys
from pathlib import Path

VERSION = '1.0.0'
MAX_QUERIES, TIMEOUT, MAX_EML = 80, 3.0, 5 * 1024 * 1024
TYPES = {'A': 1, 'NS': 2, 'CNAME': 5, 'MX': 15, 'TXT': 16, 'AAAA': 28}
HOST = re.compile(r'^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$')


class DnsError(Exception):
    pass


def domain_value(value):
    value = value.strip().rstrip('.').lower()
    try:
        value = value.encode('idna').decode('ascii')
    except UnicodeError:
        raise ValueError(f'{value!r} is not a valid domain name.')
    if not HOST.match(value):
        raise ValueError(f'{value!r} is not a valid domain name (give the bare domain, e.g. example.com).')
    return value


def org_domain(name, override=None):
    """Approximate organisational domain: the last two labels. Suffixes such as co.uk need --org-domain."""
    if override and (name == override or name.endswith('.' + override)):
        return override
    return '.'.join(name.split('.')[-2:])


# ---------------------------------------------------------------- DNS

def system_resolver():
    try:
        for line in Path('/etc/resolv.conf').read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == 'nameserver':
                return parts[1].split('%')[0]
    except OSError:
        pass
    return None


def encode_name(name):
    out = b''
    for label in name.split('.'):
        out += bytes([len(label)]) + label.encode('ascii')
    return out + b'\0'


def read_name(data, offset, depth=0):
    labels = []
    while True:
        if offset >= len(data) or depth > 20:
            raise DnsError('Malformed DNS response.')
        length = data[offset]
        if length & 0xC0 == 0xC0:
            pointer = struct.unpack('>H', data[offset:offset + 2])[0] & 0x3FFF
            name, _ = read_name(data, pointer, depth + 1)
            labels.append(name)
            return '.'.join(x for x in labels if x), offset + 2
        if length == 0:
            return '.'.join(labels), offset + 1
        labels.append(data[offset + 1:offset + 1 + length].decode('ascii', 'replace').lower())
        offset += 1 + length


def parse_response(data, ident, qtype):
    if len(data) < 12:
        raise DnsError('Short DNS response.')
    rid, flags, qd, an = struct.unpack('>HHHH', data[:8])
    if rid != ident:
        raise DnsError('DNS response id mismatch.')
    rcode = flags & 0xF
    if rcode == 3:
        return [], True
    if rcode != 0:
        raise DnsError(f'DNS server returned error code {rcode}.')
    offset = 12
    for _ in range(qd):
        _, offset = read_name(data, offset)
        offset += 4
    values = []
    for _ in range(an):
        _, offset = read_name(data, offset)
        rtype, _, _, rdlen = struct.unpack('>HHIH', data[offset:offset + 10])
        offset += 10
        rdata = data[offset:offset + rdlen]
        if rtype == qtype:
            if rtype == 16:
                parts, i = [], 0
                while i < len(rdata):
                    parts.append(rdata[i + 1:i + 1 + rdata[i]])
                    i += 1 + rdata[i]
                values.append(b''.join(parts).decode('utf-8', 'replace'))
            elif rtype == 15:
                host, _ = read_name(data, offset + 2)
                values.append(f'{struct.unpack(">H", rdata[:2])[0]} {host or "."}')
            elif rtype == 1:
                values.append(str(ipaddress.IPv4Address(rdata)))
            elif rtype == 28:
                values.append(str(ipaddress.IPv6Address(rdata)))
            elif rtype in (2, 5):
                values.append(read_name(data, offset)[0])
        offset += rdlen
    return values, False


class Resolver:
    def __init__(self, server=None, records=None):
        self.records = records
        self.server = server
        self.cache, self.queries = {}, 0
        if records is None and not server:
            raise ValueError('No DNS resolver found in /etc/resolv.conf; pass --resolver, e.g. --resolver 1.1.1.1.')

    def lookup(self, name, rtype):
        """Return (values, nxdomain)."""
        key = (name.lower().rstrip('.'), rtype)
        if key in self.cache:
            return self.cache[key]
        if self.records is not None:
            values = self.records.get(f'{key[0]} {rtype}')
            exists = values is not None or any(k.split()[0] == key[0] for k in self.records)
            result = (list(values or []), not exists)
        else:
            self.queries += 1
            if self.queries > MAX_QUERIES:
                raise DnsError(f'More than {MAX_QUERIES} DNS queries in one run; stopping.')
            result = self.query(key[0], TYPES[rtype])
        self.cache[key] = result
        return result

    def query(self, name, qtype):
        ident = random.randrange(65536)
        packet = struct.pack('>HHHHHH', ident, 0x0100, 1, 0, 0, 1) + encode_name(name) + struct.pack('>HH', qtype, 1)
        packet += b'\0' + struct.pack('>HHIH', 41, 1232, 0, 0)
        family = socket.AF_INET6 if ':' in self.server else socket.AF_INET
        last = None
        for _ in range(2):
            try:
                with socket.socket(family, socket.SOCK_DGRAM) as s:
                    s.settimeout(TIMEOUT)
                    s.sendto(packet, (self.server, 53))
                    data = s.recv(4096)
                if struct.unpack('>H', data[2:4])[0] & 0x0200:
                    with socket.create_connection((self.server, 53), timeout=TIMEOUT) as s:
                        s.sendall(struct.pack('>H', len(packet)) + packet)
                        size = struct.unpack('>H', self._recv(s, 2))[0]
                        data = self._recv(s, size)
                return parse_response(data, ident, qtype)
            except (OSError, struct.error) as error:
                last = error
        raise DnsError(f'DNS query for {name} failed via {self.server}: {last}')

    @staticmethod
    def _recv(s, size):
        data = b''
        while len(data) < size:
            chunk = s.recv(size - len(data))
            if not chunk:
                raise DnsError('DNS TCP connection closed early.')
            data += chunk
        return data

    def txt(self, name, prefix):
        values, nx = self.lookup(name, 'TXT')
        return [v for v in values if v.lower().startswith(prefix)], nx


# ---------------------------------------------------------------- checks

class Report:
    def __init__(self, domain):
        self.domain, self.findings, self.records, self.fixes = domain, [], [], []

    def add(self, severity, code, message, record=None):
        self.findings.append(dict(severity=severity, code=code, message=message, record=record))

    def seen(self, name, rtype, values):
        self.records.append(dict(name=name, type=rtype, values=values))


def check_mx(dns, report):
    values, nx = dns.lookup(report.domain, 'MX')
    report.seen(report.domain, 'MX', values)
    if nx:
        report.add('blocker', 'domain-missing', f'{report.domain} does not exist in DNS (NXDOMAIN). Receivers reject mail from non-existent domains.')
        return False
    if not values:
        report.add('warning', 'mx-missing', 'No MX record: replies and bounces to this domain have nowhere to go, and some receivers distrust sender domains that cannot receive mail.')
        return True
    for value in values:
        pref, host = value.split(' ', 1)
        if host == '.':
            if len(values) == 1:
                report.add('info', 'mx-null', 'Null MX ("0 ."): this domain declares that it receives no mail (RFC 7505). Fine for a send-only domain; replies will bounce.', f'{report.domain} MX {value}')
            continue
        try:
            ipaddress.ip_address(host)
            report.add('blocker', 'mx-ip', f'MX target {host} is an IP address; MX must name a host.', f'{report.domain} MX {value}')
            continue
        except ValueError:
            pass
        if not dns.lookup(host, 'A')[0] and not dns.lookup(host, 'AAAA')[0]:
            report.add('blocker', 'mx-unresolved', f'MX host {host} has no A or AAAA record, so mail to {report.domain} cannot be delivered there.', f'{report.domain} MX {value}')
    return True


SPF_MECH = re.compile(r'^([+\-~?]?)(all|include|a|mx|ptr|ip4|ip6|exists)(?::(.+?))?(?:/(\d+))?(?://(\d+))?$', re.I)
SPF_MOD = re.compile(r'^([a-z][a-z0-9_.\-]*)=(.*)$', re.I)


def parse_spf(record):
    """Return (terms, errors). Terms are (qualifier, mechanism, argument) or ('=', name, value)."""
    terms, errors = [], []
    for term in record.split()[1:]:
        mod = SPF_MOD.match(term)
        mech = SPF_MECH.match(term)
        if mod and not mech:
            terms.append(('=', mod.group(1).lower(), mod.group(2)))
            continue
        if not mech:
            errors.append(f'unknown term "{term}"')
            continue
        qualifier, name, arg = mech.group(1) or '+', mech.group(2).lower(), mech.group(3)
        if name in ('ip4', 'ip6'):
            try:
                net = ipaddress.ip_network(arg + (f'/{mech.group(4)}' if mech.group(4) else ''), strict=False)
                if (name == 'ip4') != (net.version == 4):
                    raise ValueError
            except (ValueError, TypeError):
                errors.append(f'invalid address in "{term}"')
                continue
        elif name in ('include', 'exists') and not arg:
            errors.append(f'"{term}" needs a domain')
            continue
        elif name == 'all' and arg:
            errors.append(f'"{term}" takes no argument')
            continue
        terms.append((qualifier, name, arg))
    return terms, errors


def check_spf(dns, report, expected=()):
    records, _ = dns.txt(report.domain, 'v=spf1')
    report.seen(report.domain, 'TXT', records)
    if not records:
        report.add('blocker', 'spf-missing', 'No SPF record. Gmail requires SPF or DKIM for every sender and both for bulk senders.')
        return None
    if len(records) > 1:
        report.add('blocker', 'spf-multiple', f'{len(records)} SPF records found. More than one is a permanent error (RFC 7208 §4.5): receivers treat SPF as failed.', ' | '.join(records))
    record = records[0]
    terms, errors = parse_spf(record)
    for error in errors:
        report.add('blocker', 'spf-syntax', f'SPF syntax error: {error}.', record)
    alls = [t for t in terms if t[1] == 'all']
    redirect = [t for t in terms if t[0] == '=' and t[1] == 'redirect']
    if alls and alls[0][0] == '+':
        report.add('blocker', 'spf-pass-all', '"+all" lets any server on the internet pass SPF for your domain.', record)
    elif alls and alls[0][0] == '?':
        report.add('warning', 'spf-neutral-all', '"?all" gives no protection; use "~all" (or "-all" once DKIM and DMARC pass).', record)
    elif not alls and not redirect:
        report.add('warning', 'spf-no-all', 'No "all" term: unlisted servers get a neutral result. End the record with "~all".', record)
    if any(t[1] == 'ptr' for t in terms):
        report.add('warning', 'spf-ptr', '"ptr" is deprecated (RFC 7208 §5.5), slow, and ignored by some receivers.', record)
    return dict(record=record, terms=terms)




DMARC_TAGS = {'v', 'p', 'sp', 'pct', 'rua', 'ruf', 'adkim', 'aspf', 'fo', 'rf', 'ri', 'np', 't', 'psd'}


def parse_dmarc(record):
    tags, errors = {}, []
    parts = [p.strip() for p in record.split(';') if p.strip()]
    for index, part in enumerate(parts):
        if '=' not in part:
            errors.append(f'"{part}" is not a tag=value pair')
            continue
        key, value = (x.strip() for x in part.split('=', 1))
        key = key.lower()
        if index == 0 and (key != 'v' or value != 'DMARC1'):
            errors.append('the record must start with "v=DMARC1"')
        if key not in DMARC_TAGS:
            errors.append(f'unknown tag "{key}"')
        tags[key] = value
    for key in ('p', 'sp', 'np'):
        if key in tags and tags[key].lower() not in ('none', 'quarantine', 'reject'):
            errors.append(f'{key}={tags[key]} must be none, quarantine or reject')
    for key in ('adkim', 'aspf'):
        if key in tags and tags[key].lower() not in ('r', 's'):
            errors.append(f'{key}={tags[key]} must be r or s')
    if 'pct' in tags and not (tags['pct'].isdigit() and 0 <= int(tags['pct']) <= 100):
        errors.append(f'pct={tags["pct"]} must be 0-100')
    return tags, errors


def check_dmarc(dns, report, org_override=None):
    name = f'_dmarc.{report.domain}'
    records, _ = dns.txt(name, 'v=dmarc1')
    report.seen(name, 'TXT', records)
    inherited = False
    org = org_domain(report.domain, org_override)
    if not records and org != report.domain:
        name = f'_dmarc.{org}'
        records, _ = dns.txt(name, 'v=dmarc1')
        report.seen(name, 'TXT', records)
        inherited = bool(records)
    if not records:
        misplaced = [v for v in dns.lookup(f'_dmarc.{report.domain}', 'TXT')[0] if 'v=dmarc1' in v.lower()]
        if misplaced:
            report.add('blocker', 'dmarc-syntax', f'The TXT record at _dmarc.{report.domain} does not start with "v=DMARC1", so receivers ignore it. Put v=DMARC1 first.', misplaced[0])
            return None
        report.add('blocker', 'dmarc-missing', f'No DMARC record at _dmarc.{report.domain}. Gmail and Yahoo require DMARC for bulk senders, and without it you get no reports about spoofing or failures.')
        return None
    if len(records) > 1:
        report.add('blocker', 'dmarc-multiple', f'{len(records)} DMARC records at {name}; receivers ignore DMARC when there is more than one.', ' | '.join(records))
    record = records[0]
    tags, errors = parse_dmarc(record)
    for error in errors:
        report.add('blocker' if 'v=DMARC1' in error or 'must be' in error else 'warning', 'dmarc-syntax', f'DMARC syntax: {error}.', record)
    policy = (tags.get('sp') if inherited and 'sp' in tags else tags.get('p', '')).lower()
    if inherited:
        report.add('info', 'dmarc-inherited', f'No record at _dmarc.{report.domain}; the organisational domain\'s record applies (policy "{policy or "none"}").', record)
    if 'p' not in tags:
        report.add('warning', 'dmarc-no-policy', 'No "p=" tag; receivers treat the policy as none.', record)
    elif policy == 'none':
        report.add('warning', 'dmarc-monitor-only', 'Policy is "none": you get reports, but spoofed mail is still delivered. Move to quarantine and then reject once reports show your own mail passes (see references/rollout.md).', record)
    if policy in ('quarantine', 'reject') and tags.get('pct', '100') != '100':
        report.add('warning', 'dmarc-partial', f'pct={tags["pct"]}: the policy applies to only part of failing mail.', record)
    rua = [u.strip() for u in tags.get('rua', '').split(',') if u.strip()]
    if not rua:
        report.add('warning', 'dmarc-no-reports', 'No "rua=" address, so you receive no aggregate reports and cannot see which senders fail.', record)
    for uri in rua:
        if not uri.lower().startswith('mailto:') or '@' not in uri:
            report.add('blocker', 'dmarc-rua-syntax', f'Report address "{uri}" must be a mailto: URI.', record)
            continue
    return dict(record=record, tags=tags, inherited=inherited)




def run(domain, dns, selectors=(), provider=None, eml=None, org=None, bulk=False):
    report = Report(domain_value(domain))
    report.spf_lookups = report.dkim_selectors = report.eml = None
    exists = check_mx(dns, report)
    spf = dmarc = None
    if exists:
        spf = check_spf(dns, report)
        dmarc = check_dmarc(dns, report, org)
    order = {'blocker': 0, 'warning': 1, 'info': 2}
    report.findings.sort(key=lambda f: order[f['severity']])
    blockers = sum(f['severity'] == 'blocker' for f in report.findings)
    warnings = sum(f['severity'] == 'warning' for f in report.findings)
    return dict(tool='email-deliverability-check', version=VERSION, domain=report.domain,
                source='records file' if dns.records is not None else f'DNS via {dns.server}',
                blocking=blockers, warnings=warnings, findings=report.findings, records=report.records,
                fixes=report.fixes, spf_lookups=report.spf_lookups, dkim_selectors=report.dkim_selectors,
                message=report.eml, dns_queries=dns.queries)


def markdown(result):
    label = {0: 'Ready: no blocking problems in the checked records.'}.get(result['blocking'], f'Not ready: {result["blocking"]} blocking problem(s).')
    lines = [f'# Email deliverability check: {result["domain"]}', '',
             f'**{label}** {result["warnings"]} warning(s). Source: {result["source"]}.', '']
    if result['spf_lookups'] is not None:
        lines += [f'- SPF DNS lookups: {result["spf_lookups"]} of 10']
    if result['dkim_selectors'] is not None:
        lines += [f'- DKIM keys found: {", ".join(result["dkim_selectors"]) or "none"}']
    if result['message']:
        m = result['message']
        lines += [f'- Received message from {m["from_domain"]}: spf={m["spf"]}, dkim={",".join(m["dkim"]) or "none"}, dmarc={m["dmarc"]}']
    lines += (['', '## Findings', ''] if lines[-1] else ['## Findings', ''])
    if not result['findings']:
        lines.append('None.')
    for f in result['findings']:
        lines.append(f'- **{f["severity"].upper()}** `{f["code"]}`: {f["message"]}')
        if f['record']:
            lines.append(f'  - Evidence: `{f["record"]}`')
    if result['fixes']:
        lines += ['', '## Records to publish', '', 'Edit these at your DNS host. Values are shown without surrounding quotes.', '']
        for fix in result['fixes']:
            lines += [f'- `{fix["name"]}` {fix["type"]}', f'  ```', f'  {fix["value"]}', f'  ```', f'  {fix["why"]}']
    lines += ['', '## Records read', '']
    for r in result['records']:
        lines.append(f'- `{r["name"]}` {r["type"]}: ' + (' | '.join(f'`{v}`' for v in r['values']) if r['values'] else 'none'))
    lines += ['', '## Not checked here', '',
              '- Sending IP and domain reputation, blocklists, spam complaint rate (see Google Postmaster Tools).',
              '- Reverse DNS of your provider\'s sending IPs, TLS on your provider\'s servers, message content.',
              '- DNS changes can take up to the record TTL to be visible; rerun after publishing.', '']
    lines += ['Lite edition: DKIM keys, SPF lookups through includes, received-message alignment and records to publish are in the full version: https://ohayo.si/skills/email-deliverability-check/', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check a sending domain\'s MX, SPF, DKIM and DMARC records.')
    parser.add_argument('domain')
    parser.add_argument('--resolver', help='DNS server IP (default: first nameserver in /etc/resolv.conf)')
    parser.add_argument('--records', help='read records from a JSON file instead of DNS ("name TYPE": [values])')
    parser.add_argument('--org-domain', help='organisational domain when the suffix has two labels, e.g. example.co.uk')
    parser.add_argument('--output', help='write the Markdown report here')
    parser.add_argument('--json', help='write the JSON result here')
    args = parser.parse_args(argv)
    try:
        records = None
        if args.records:
            raw = json.loads(Path(args.records).read_text(encoding='utf-8'))
            records = {k.lower().rsplit(' ', 1)[0].rstrip('.') + ' ' + k.rsplit(' ', 1)[1].upper(): v for k, v in raw.items() if not k.startswith('_comment')}
        dns = Resolver(args.resolver or system_resolver(), records)
        org = domain_value(args.org_domain) if args.org_domain else None
        result = run(args.domain, dns, org=org)
    except (ValueError, DnsError, OSError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    text = markdown(result)
    if args.output:
        Path(args.output).write_text(text, encoding='utf-8')
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(text if not args.output else f'{result["domain"]}: {result["blocking"]} blocking, {result["warnings"]} warnings -> {args.output}')
    return 1 if result['blocking'] else 0


if __name__ == '__main__':
    sys.exit(main())
