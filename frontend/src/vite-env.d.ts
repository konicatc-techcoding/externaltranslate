/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute WebSocket URL used in dev; empty in a production build. */
  readonly VITE_WS_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
