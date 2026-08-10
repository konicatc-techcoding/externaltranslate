import { ControlPage } from "./pages/ControlPage";
import { OverlayPage } from "./pages/OverlayPage";
import "./styles.css";

interface AppProps {
  pathname?: string;
}

/**
 * Two pages only, split on pathname. A router dependency would buy nothing
 * for v0.1.
 */
export function App({ pathname }: AppProps = {}) {
  const path = pathname ?? window.location.pathname;
  return path.replace(/\/+$/, "") === "/overlay" ? <OverlayPage /> : <ControlPage />;
}
