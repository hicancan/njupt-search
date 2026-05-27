# Exam Core Package Migration Target

This directory is the Milestone 4 target for pure exam-domain logic. It is README-only until exam logic and tests are moved.

Near-term migration purpose:

- own exam model helpers and contract-facing pure logic;
- own class/course search behavior currently covered by `useClassSearch`, `examQuery`, and generated data tests;
- own `.ics` calendar/export logic currently in `src/utils/icsGenerator.ts`.

React hooks and UI remain in the web app; this package should contain browser-safe pure domain code.

