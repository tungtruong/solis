# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.

## Local Frontend-Only Mode

This workspace is configured so local UI can proxy `/api` to a deployed backend (shared cloud database).

1. Copy `web/.env.local.example` to `web/.env.local`.
2. Set `VITE_API_PROXY_TARGET` to your deployed host, for example:

```env
VITE_API_PROXY_TARGET=https://wssmeas-mvp-202603152044.web.app
```

3. Start local UI (`npm run dev` in `web/`) or run `./scripts/start_local_fast.ps1` from workspace root.
