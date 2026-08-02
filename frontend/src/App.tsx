import { zhTW } from "./i18n/zh-TW";
import "./styles.css";

export function App() {
  return (
    <main className="app-shell">
      <section className="status-card" aria-labelledby="product-title">
        <p className="eyebrow">Stage 0</p>
        <h1 id="product-title">{zhTW.productName}</h1>
        <p>{zhTW.productDescription}</p>
        <output className="status-badge" aria-live="polite">
          {zhTW.setupStatus.notChecked}
        </output>
      </section>
    </main>
  );
}
