# Court Signup App

Court reservation/queue webapp for a badminton/tennis/pickleball venue. React + Django + Postgres, local dev for now (production hosting TBD).

See `/Users/wesleyhsieh/.claude/plans/i-want-to-build-gleaming-barto.md` for the original implementation plan (architecture, data model, API, lifecycle diagrams).

## Planning conventions for this project

- When presenting a plan, use diagrams (ASCII/mermaid) for architecture and state machines instead of long prose — keep the rest of the plan concise, not verbose.
- Every plan for a non-trivial change must include an explicit test-based Definition of Done: concrete Given/When/Then test cases with real example data, not just categories. A task isn't done until those cases pass, not just when the code is written.
