import { zhTW } from "../i18n/zh-TW";
import type { ComponentStatus } from "../types/runtime";

interface ComponentStatusListProps {
  components: ComponentStatus[];
  stale?: boolean;
}

export function ComponentStatusList({
  components,
  stale = false,
}: ComponentStatusListProps) {
  return (
    <section
      className="panel"
      aria-labelledby="components-title"
      data-stale={stale ? "true" : "false"}
    >
      <h2 id="components-title">{zhTW.components.title}</h2>
      {stale ? <p className="panel__warning">{zhTW.components.stale}</p> : null}
      <ul className="component-list">
        {components.map((component) => (
          <li key={component.component} data-state={component.state}>
            <span>{zhTW.components.labels[component.component]}</span>
            <span className="component-list__state">{component.state}</span>
            {/* detail is composed from the backend whitelist: metadata only */}
            {component.detail !== null ? (
              <span className="component-list__detail">{component.detail}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
