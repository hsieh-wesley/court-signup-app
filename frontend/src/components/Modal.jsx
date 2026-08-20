import { useEffect, useRef } from "react";
import { X } from "lucide-react";

// Shared backdrop + card wrapper for every modal in the app (Add Player,
// Manage Court/Location/Membership, Court Join). Clicking the backdrop or
// pressing Escape closes it; clicking inside the card does not.
export default function Modal({ title, onClose, children, className = "" }) {
  const cardRef = useRef(null);

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    cardRef.current?.focus();
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

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
