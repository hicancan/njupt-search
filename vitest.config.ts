import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './apps/web/src'),
    },
  },
  test: {
    include: [
      'apps/web/src/**/*.test.{ts,tsx}',
      'packages/**/*.test.{ts,tsx}',
    ],
  },
});
