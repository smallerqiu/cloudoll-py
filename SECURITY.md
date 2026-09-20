# Security policy

Cloudoll core provides infrastructure, not an application authorization policy.
Generated templates are examples: applications own authorization, upload policy,
CSRF protection where applicable, secret management and deployment configuration.

## Reporting

Do not publish credentials or exploitable details in a public issue. Report a
suspected vulnerability privately to the maintainer at smallerqiu@gmail.com
(the package's published contact). Include affected versions, a minimal sanitized
reproduction, impact and any mitigation. No response-time SLA is promised.

## Maintenance scope

Security fixes target the latest stable release. Older release branches have no
guaranteed backports; upgrade or contact the maintainer about a specific issue.
This policy accompanies Cloudoll 4.0.0; published versions are identified by PyPI
and repository release tags, not by documentation edits alone.
CI compatibility with a Python version is not an extension of that runtime's
upstream security support. Deploy on a runtime still supported by its vendor.

Dependency audit CI checks the resolved native/cache/AWS dependencies. A clean
audit means no known advisories were reported for that resolution, not proof that
the project is vulnerability-free. Aurora runtime/failover remains unverified.

Do not enable SQL parameter echo in production without a data-handling review.
Structured JSON data masks common secret keys; arbitrary strings, SQL literals,
exception messages and personal data require an application-specific redactor.
