# 映序 CineFlow — Frontend

Web UI for **CineFlow**（映序）: chat-driven video creation for product stories, social content, and brand marketing. Built with Next.js 16, React 19 and Tailwind CSS 4. It talks to the Python backend in `../backend`.

## Commands

```bash
npm install        # install dependencies
npm run dev        # dev server on http://localhost:3000
npm run lint       # ESLint
npm run build      # production build
npm start          # serve the production build (next start)
```

## Environment variables

Copy `.env.example` to `.env.local` and adjust. All of these are read at **build time** — rebuild after changing them.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BACKEND_API_URL` | `http://127.0.0.1:8000` | Target of the `/api/*` and `/code/*` rewrites in `next.config.ts` |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Base URL the browser uses for direct SSE streaming connections |
| `NEXT_PUBLIC_APP_NAME` | `映序 CineFlow` | Product name (page title, sidebar, top bar) |
| `NEXT_PUBLIC_APP_TAGLINE` | `把灵感变成连贯的镜头故事` | Tagline / meta description |

## Branding

Branding lives in `config/brand.ts` (`brand.name`, `brand.tagline`, `brand.storagePrefix`). To re-skin:

- set the `NEXT_PUBLIC_APP_*` variables, or edit the defaults in `config/brand.ts`;
- theme styles use the `sfa-` class prefix in `app/globals.css`;
- localStorage keys are namespaced with `brand.storagePrefix` (default `sfa`).

## Docker

```bash
docker build -t cineflow-frontend \
  --build-arg BACKEND_API_URL=http://backend:8000 \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 \
  .
docker run -p 3000:3000 cineflow-frontend
```
