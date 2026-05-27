# Web App Migration Target

This directory is the Milestone 5 target for the React/Vite/PWA product. It is intentionally README-only during Milestone 1 so production behavior continues to run from the current root `src/`, `public/`, `index.html`, and `vite.config.ts` layout.

Near-term migration purpose:

- receive the current browser application when Milestone 5 moves the Vite app;
- become the owner of routing, pages, widgets, Worker integration, PWA config, and generated public runtime assets;
- preserve current public URLs until the generated artifact layout migration has passed browser acceptance and CI.

Do not move source code here before the milestone that explicitly owns the move.

