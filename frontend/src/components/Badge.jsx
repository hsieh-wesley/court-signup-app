// One shared status pill instead of five inline implementations —
// `status` maps to a badge-* color class, `label` is always plain text
// (never color-only) so it reads without relying on hue perception.
const STATUS_CLASSES = {
  success: "badge-success",
  warning: "badge-warning",
  danger: "badge-danger",
  info: "badge-info",
  accent: "badge-accent",
  neutral: "badge-neutral",
};

export default function Badge({ status = "neutral", children }) {
  const className = `badge ${STATUS_CLASSES[status] || STATUS_CLASSES.neutral}`;
  return <span className={className}>{children}</span>;
}
