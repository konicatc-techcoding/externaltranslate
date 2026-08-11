import { useEffect, useState, type ReactNode } from "react";

interface CollapsiblePanelProps {
  title: string;
  /** Short line shown beside the title, readable while collapsed. */
  summary?: string;
  children: ReactNode;
  /** Starting state when the caller does not control `open`. */
  defaultOpen?: boolean;
  /** Controlled state; pair with `onOpenChange` to persist it. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /**
   * Opens the panel when this becomes true — used when the panel starts
   * reporting a problem. Tidying the page is not worth hiding a fault, but
   * the operator can still close it again afterwards.
   */
  openOnProblem?: boolean;
}

/**
 * A panel that folds away.
 *
 * Built on `<details>` so the disclosure semantics, keyboard handling and
 * screen-reader behaviour come from the browser rather than from a div and a
 * click handler.
 */
export function CollapsiblePanel({
  title,
  summary,
  children,
  defaultOpen = false,
  open,
  onOpenChange,
  openOnProblem = false,
}: CollapsiblePanelProps) {
  const [uncontrolled, setUncontrolled] = useState(defaultOpen || openOnProblem);
  const isOpen = open ?? uncontrolled;

  useEffect(() => {
    if (openOnProblem) {
      setUncontrolled(true);
      onOpenChange?.(true);
    }
    // Only react to the problem appearing, not to the handler identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openOnProblem]);

  return (
    <details
      className="panel panel--collapsible"
      open={isOpen}
      onToggle={(event) => {
        const next = event.currentTarget.open;
        setUncontrolled(next);
        if (next !== isOpen) {
          onOpenChange?.(next);
        }
      }}
    >
      <summary className="panel__summary">
        <span className="panel__summary-title">{title}</span>
        {summary !== undefined ? (
          <span className="panel__summary-note">{summary}</span>
        ) : null}
      </summary>
      <div className="panel__body">{children}</div>
    </details>
  );
}
