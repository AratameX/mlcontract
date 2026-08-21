# Security policy

## Supported versions

While the project is pre-1.0, only the latest release receives security fixes.

| Version | Supported |
| --- | --- |
| Latest `0.x` | Yes |
| Older `0.x` | No |

## Reporting a vulnerability

**Please do not open a public issue.**

Use GitHub's private reporting: **Security → Report a vulnerability** on this
repository. That creates a channel visible only to the maintainers.

If that is unavailable, email **hawkeyes1818@gmail.com** with `schemapact
security` in the subject.

Please include what you can: affected version, what an attacker could achieve,
and the smallest reproduction you have. A working proof of concept is welcome
but not required — a clear description of the mechanism is enough to start.

### What to expect

- **Acknowledgement within 7 days.** This is a spare-time project maintained by
  one person, so that is a realistic commitment rather than an aspirational one.
- An assessment of severity and a fix timeline once the report is understood.
- Credit in the release notes, unless you would rather not be named.

## Threat model

Knowing what this library does and does not defend against saves everyone time.

**Contracts are treated as untrusted input.** They often arrive from another
team or repository. YAML is parsed with `safe_load`, so a contract file cannot
construct arbitrary Python objects, and unknown keys are rejected rather than
interpreted.

**Regular expressions in contracts are not sandboxed.** A `pattern` is compiled
and run by Python's `re` module, so a contract author can write an expression
with catastrophic backtracking and make validation extremely slow against
crafted input. If you accept contracts from parties you do not trust, review
their patterns, and consider a timeout around validation.

**Reports may contain data.** Violations carry sampled offending values by
default, because that is what makes them actionable. If reports are written
somewhere with a weaker trust boundary than the data — a shared build log, an
error aggregator — pass `sample_values=False` or `--no-samples`.

**Data is not sanitised.** This library reads data to check it; it does not
attempt to render it safely elsewhere. Escaping is the responsibility of
whatever consumes a report.

**Out of scope:** vulnerabilities in pandas, PyYAML or other dependencies —
report those upstream, though we welcome a heads-up so the floor can be raised.

## Supply chain

- Releases are published from a tagged commit via GitHub Actions using PyPI
  Trusted Publishing, so no long-lived API token exists to be stolen.
- Dependencies are monitored by Dependabot and audited by `pip-audit` in CI.
- The core has no required runtime dependencies, which is a security property as
  well as a design one: it is the smallest possible attack surface.
