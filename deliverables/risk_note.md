1. AUTHOR:  Internal support-ops team -- verify ownership by checking their repo, commit history, and deployment pipeline before trusting.
2. REACH:   The server token grants read access to every ticket the service account can see, not just the ones your agent asks about.
3. LOGGING: The server logs ticket_id and caller IP on every tools/call -- those logs contain PII and must be treated accordingly.
4. STOLEN TOKEN: An attacker with the bearer token can enumerate all tickets, read escalation history, and pivot to customer PII without ever touching your agent.
5. SHIP?:   Yes, only if the server is owned by a known internal team, runs inside the company VPC, and the token is scoped to read-only with a short TTL (hours, not months).
