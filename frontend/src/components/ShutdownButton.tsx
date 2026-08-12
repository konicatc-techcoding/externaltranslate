import { useEffect, useRef, useState } from "react";

import { zhTW } from "../i18n/zh-TW";

interface ShutdownButtonProps {
  /** Warned about in the dialog: closing now takes the captions off air. */
  running: boolean;
  onConfirm: () => void;
}

/**
 * Ends the program from the control page.
 *
 * A packaged build shows the operator a browser tab; the console window that
 * would otherwise be the way out can be behind everything else or minimised.
 *
 * It asks first, in a modal. Unlike the vMix switch — where a dialog stealing
 * focus mid-show would be worse than the mistake — there is nothing to return
 * to afterwards, and the cost of a mis-click is the whole program.
 */
export function ShutdownButton({ running, onConfirm }: ShutdownButtonProps) {
  const [asking, setAsking] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = dialog.current;
    if (element === null) {
      return;
    }
    if (asking && !element.open) {
      element.showModal();
    } else if (!asking && element.open) {
      element.close();
    }
  }, [asking]);

  return (
    <>
      <button
        type="button"
        className="button-danger"
        onClick={() => setAsking(true)}
      >
        {zhTW.shutdown.button}
      </button>

      <dialog
        ref={dialog}
        className="confirm-dialog"
        aria-label={zhTW.shutdown.title}
        // Esc closes the dialog natively; keep React's state in step with it.
        onClose={() => setAsking(false)}
      >
        <h2>{zhTW.shutdown.title}</h2>
        <p>{running ? zhTW.shutdown.warningRunning : zhTW.shutdown.warning}</p>
        <div className="field-row">
          <button
            type="button"
            className="button-danger"
            onClick={() => {
              setAsking(false);
              onConfirm();
            }}
          >
            {zhTW.shutdown.confirm}
          </button>
          <button type="button" onClick={() => setAsking(false)}>
            {zhTW.shutdown.cancel}
          </button>
        </div>
      </dialog>
    </>
  );
}
