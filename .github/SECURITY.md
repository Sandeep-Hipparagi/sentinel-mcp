# Security Policy

## Supported versions

| Version | Supported |
| :--- | :--- |
| latest `main` | yes |
| older tags | no |

## Reporting a vulnerability

Do **not** open a public issue for security reports.

Email **hipparagi95@gmail.com** with:

1. A description of the issue and its impact.
2. Reproduction steps or a proof-of-concept.
3. The commit SHA you tested against.

You will receive an acknowledgement within 72 hours. Please allow up to 90 days
for a fix before public disclosure; coordinated disclosure is preferred.

## Scope

- The MCP server, transport adapters, and all bundled tools
  (verification, policy gate, WORM audit ledger, graph memory).
- The conformance self-test and packaging metadata.
- Out of scope: client applications connecting to the server, and issues
  requiring a hostile local environment.
