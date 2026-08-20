import { useEffect, useRef } from "react";
import { X } from "lucide-react";

// Shared backdrop + card wrapper for every modal in the app (Add Player,
// Manage Court/Location/Membership, Court Join). Clicking the backdrop or
// pressing Escape closes it; clicking inside the card does not.
export default function Modal({ title, onClose, children, className = "" }) {
  const cardRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Focus-on-open must run exactly once, at mount — not on every render
  // where `onClose` happens to be a new function identity (e.g. an inline
  // arrow prop recreated by a parent re-render on every keystroke inside
  // the modal's own form). Re-focusing the card on each of those renders
  // was yanking focus away from whatever input the user was actively
  // typing into. The Escape listener still always calls the latest
  // onClose via the ref, without needing to be in this effect's deps.
  useEffect(() => {
    cardRef.current?.focus();
  }, []);

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape") onCloseRef.current();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={cardRef}
        className={`modal card ${className}`.trim()}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <button
          type="button"
          className="btn btn-ghost btn-icon modal-close"
          onClick={onClose}
          aria-label="Close"
        >
          <X size={16} />
        </button>
        {title && <h3>{title}</h3>}
        {children}
      </div>
    </div>
  );
}
