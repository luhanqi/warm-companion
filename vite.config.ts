import { defineConfig } from 'vite'

const PAGE_ALIASES: Record<string, string> = {
  '/': '/login.html',
  '/login': '/login.html',
  '/talk': '/talk.html',
  '/nostalgia': '/nostalgia.html',
  '/memoir': '/memoir.html',
  '/garden': '/garden.html',
  '/life': '/life.html',
  '/paint': '/paint.html',
  '/observe': '/observe.html',
  '/games': '/games.html',
  '/memory': '/memory.html',
  '/profile': '/profile.html',
  '/family': '/family.html',
  '/care': '/care.html',
  '/gift': '/gift.html',
  '/companion': '/talk.html',
}

export default defineConfig({
  root: 'web',
  publicDir: false,
  plugins: [
    {
      name: 'html-page-aliases',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const path = (req.url || '').split('?')[0]
          const target = PAGE_ALIASES[path]
          if (target) {
            res.writeHead(302, { Location: target })
            res.end()
            return
          }
          next()
        })
      },
    },
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
})
