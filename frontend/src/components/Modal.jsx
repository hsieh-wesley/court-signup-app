// Shared backdrop + card wrapper, reusing the `.modal-backdrop`/`.modal`
// CSS OverviewPage's CourtJoinModal already established. Clicking the
// backdrop closes the modal; clicking inside the card does not.
export default function Modal({ title, onClose, children, className = "" }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal card ${className}`.trim()} onClick={(e) => e.stopPropagation()}>
        {title && <h3>{title}</h3>}
        {children}
      </div>
    </div>
  );
}
