# Security Policy

Security matters especially for Komponist because it processes organization
knowledge, connector credentials, API keys, and permission-scoped context.

## Supported versions

Komponist is currently an early-stage MVP. Security fixes are applied to the
latest commit on the `main` branch. There are no supported historical release
lines yet.

| Version | Supported |
| --- | --- |
| Latest `main` | Yes |
| Older commits or forks | No |

## Reporting a vulnerability

**Do not open a public issue, discussion, or pull request for a suspected
security vulnerability.**

Use GitHub's private vulnerability reporting flow:

1. Open the repository's **Security** tab.
2. Select **Advisories**.
3. Select **Report a vulnerability**.
4. Include the affected component, reproduction steps, impact, and any
   suggested mitigation.

If private vulnerability reporting is unavailable, do not publish technical
details. Contact the repository maintainers through the
[`komponist-ai`](https://github.com/komponist-ai) organization and ask for a
private reporting channel.

Please include:

- the affected route, service, package, or connector;
- the tested commit or deployment version;
- prerequisites and minimal reproduction steps;
- the expected and observed behavior;
- the security impact and affected data or permissions;
- logs or screenshots with credentials and personal data removed;
- whether the issue is already being actively exploited.

## What to expect

We aim to:

- acknowledge a report within 72 hours;
- provide an initial severity assessment within 7 days;
- send progress updates at least every 14 days while remediation is active;
- coordinate disclosure after a fix is available.

Timelines may vary while the project is maintained by a small early-stage team.
Please give us a reasonable opportunity to investigate and remediate the issue
before public disclosure.

## Scope

Reports are especially useful for:

- authentication, session, invitation, and organization-isolation bypasses;
- department visibility or authorization failures;
- API-key, MCP-key, OAuth-token, or connector-secret exposure;
- webhook signature bypasses or replay issues;
- prompt injection that crosses an enforced trust or permission boundary;
- source citation or retrieval behavior that leaks inaccessible documents;
- unsafe file parsing, path traversal, SSRF, injection, or code execution;
- vulnerabilities in the public pilot at
  [komponist.build](https://komponist.build).

The following are normally out of scope unless they demonstrate concrete
security impact:

- missing features already documented as MVP limitations;
- denial-of-service reports that require unrealistic local access;
- automated scanner output without a reproducible issue;
- social engineering, spam, or physical attacks;
- vulnerabilities that only affect an unsupported modified fork.

## Research guidelines

When testing:

- use accounts and organizations you control;
- do not access, modify, or retain another person's data;
- do not disrupt the public pilot or degrade availability;
- do not run destructive tests against production;
- do not use leaked credentials or attempt social engineering;
- stop and report immediately if you encounter real user data.

Good-faith research that follows this policy will not be intentionally pursued
as malicious activity by the project maintainers. This statement does not
authorize actions that violate applicable law or third-party terms.

## Secrets accidentally committed to Git

If you find a credential in the repository or its history, report it privately
even if it appears expired. Do not test the credential. Maintainers should
revoke or rotate it first and then remove it from the repository history where
appropriate.
