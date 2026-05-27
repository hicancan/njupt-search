# Exam Core Package

Pure exam-domain package for the web product and future tools.

It owns:

- generated exam data parsing and manifest consistency checks;
- class query routing and class/course search behavior;
- `.ics` calendar/export generation.

The web app imports this domain logic through `apps/web/src/features/exam-search`.
