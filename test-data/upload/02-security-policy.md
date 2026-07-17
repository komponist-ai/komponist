# AI and Data Security Policy

This policy applies to the Komponist MVP and all customer workspaces.

Constraint: OpenAI credentials must remain server-managed and must never be exposed to workspace users or browser code.

Constraint: Every MCP credential must be scoped to exactly one organization and stored only as a cryptographic hash.

Decision: Komponist will use separate revocable API keys for every agent or device.

Decision: Uploaded raw documents are processed in memory and are not retained after extraction.

Goal: Pass an organization-isolation test before inviting the first external design partner.

Project: Add audit logs for API-key creation, use, rotation, and revocation.
