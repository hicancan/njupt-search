import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  root: __dirname,
  publicDir: path.resolve(__dirname, 'public'),
  build: {
    outDir: path.resolve(__dirname, '../../dist'),
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      includeAssets: ['assets/logo.png', 'assets/icon-192x192.png', 'assets/icon-512x512.png'],
      manifest: {
        name: 'njupt-search',
        short_name: 'njupt-search',
        description: '南邮学生信息入口：搜公告、考试、竞赛、讲座、项目和资料',
        theme_color: '#ffffff',
        background_color: '#ffffff',
        start_url: '/',
        display: 'standalone',
        icons: [
          {
            src: 'assets/icon-192x192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'assets/icon-512x512.png',
            sizes: '512x512',
            type: 'image/png'
          }
        ]
      },
      workbox: {
        cleanupOutdatedCaches: true,
        skipWaiting: true,
        clientsClaim: true,
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.endsWith('/generated/collections/njupt-public/manifest.json'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'njupt-search-manifest-progressive',
              expiration: {
                maxEntries: 4,
                maxAgeSeconds: 60 * 5
              },
              cacheableResponse: {
                statuses: [0, 200]
              },
              broadcastUpdate: {
                channelName: 'search-data-update-channel',
                options: {}
              }
            }
          },
          {
            urlPattern: ({ url }) => url.pathname.includes('/generated/collections/njupt-public/sitegraph/jwc/artifacts/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'njupt-search-sitegraph-index-progressive',
              expiration: {
                maxEntries: 40,
                maxAgeSeconds: 60 * 60 * 24 * 365
              },
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          {
            urlPattern: ({ url }) => url.pathname.includes('/generated/collections/njupt-public/sitegraph/jwc/shards/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'njupt-search-sitegraph-shards-progressive',
              expiration: {
                maxEntries: 650,
                maxAgeSeconds: 60 * 60 * 24 * 365
              },
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          {
            urlPattern: ({ url }) => url.pathname.includes('/generated/exam/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'njupt-search-exam-data-current',
              expiration: {
                maxEntries: 12,
                maxAgeSeconds: 60 * 60 * 24 * 30
              },
              cacheableResponse: {
                statuses: [0, 200]
              },
              broadcastUpdate: {
                channelName: 'search-data-update-channel',
                options: {}
              }
            }
          }
        ]
      }
    })
  ],
})
