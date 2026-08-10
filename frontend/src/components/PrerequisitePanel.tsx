import { zhTW } from "../i18n/zh-TW";
import type { PrerequisiteItem } from "../types/runtime";

interface PrerequisitePanelProps {
  items: PrerequisiteItem[];
  busy?: boolean;
  onRefresh: () => void;
}

export function PrerequisitePanel({
  items,
  busy = false,
  onRefresh,
}: PrerequisitePanelProps) {
  return (
    <section className="panel" aria-labelledby="prerequisite-title">
      <div className="panel__header">
        <h2 id="prerequisite-title">{zhTW.prerequisites.title}</h2>
        <button type="button" onClick={onRefresh} disabled={busy}>
          {zhTW.prerequisites.refresh}
        </button>
      </div>
      <ul className="prerequisite-list">
        {items.map((item) => (
          <li key={item.identifier} data-status={item.status}>
            <span className="prerequisite-list__label">{item.label}</span>
            {/* not_checked is reported as-is: never dressed up as ready */}
            <span className="prerequisite-list__status">
              {zhTW.prerequisites.statusLabels[item.status]}
            </span>
            {item.version !== null ? (
              <span className="prerequisite-list__version">{item.version}</span>
            ) : null}
            {item.action ? (
              <span className="prerequisite-list__action">{item.action}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
