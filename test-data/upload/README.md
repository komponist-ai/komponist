# Document upload test pack

Upload `01-product-strategy.md`, `02-security-policy.md`, and
`03-customer-interview.txt` together from **Add Source → Upload Documents**.

Expected behavior:

- all three files are processed;
- extracted Decisions, Goals, Constraints, and Projects appear in Review Queue;
- each proposed entity has a citation beginning with `upload:`;
- confirming entities makes them visible in Graph and available to cited chat;
- uploading the same files again does not create duplicate facts.

The documents deliberately overlap on trust, citations, and organization
isolation so semantic search can be tested after confirmation.
