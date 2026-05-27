# Web App

This directory owns the React/Vite/PWA product.

Current boundary:

- `src/` owns the web UI, hooks, Worker integration, and feature composition.
- `index.html` and `vite.config.ts` are the Vite entry and PWA configuration.
- `public/generated/` is the only runtime generated artifact layout.
- Root `dist/` remains the build output consumed by GitHub Pages deployment.

Use the root npm scripts for development and validation so CI behavior remains stable.
