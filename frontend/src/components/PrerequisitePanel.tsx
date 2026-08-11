import { CollapsiblePanel } from "./CollapsiblePanel";
import { zhTW } from "../i18n/zh-TW";
import type { PrerequisiteItem } from "../types/runtime";

/** Statuses that mean something the operator has to act on. */
const BLOCKING = new Set(["missing"]);

interface PrerequisitePanelProps {
  items: PrerequisiteItem[];
  busy?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  onRefresh: () => void;
}

export function PrerequisitePanel({
  items,
  busy = false,
  open,
  onOpenChange,
  onRefresh,
}: PrerequisitePanelProps) {
  const problems = items.filter((item) => BLOCKING.has(item.status));
  const summary =
    items.length === 0
      ? zhTW.prerequisites.notChecked
      : problems.length > 0
        ? zhTW.prerequisites.problems.replace("{count}", String(problems.length))
        : zhTW.prerequisites.allReady;

  return (
    <CollapsiblePanel
      title={zhTW.prerequisites.title}
      summary={summary}
      open={open}
      onOpenChange={onOpenChange}
      // Once everything is ready this is reference material, not a control.
      // A missing prerequisite pops it back open.
      openOnProblem={problems.length > 0}
    >
      <div className="field-row">
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
    </CollapsiblePanel>
  );
}
