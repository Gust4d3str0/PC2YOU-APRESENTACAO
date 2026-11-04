import { Link } from 'react-router-dom';

export default function EmptyState({ icon, title, text, actionLabel, actionTo, onAction }) {
  return (
    <section className="state-panel empty-panel">
      <div className="state-icon" aria-hidden="true">{icon}</div>
      <h2>{title}</h2>
      <p>{text}</p>
      {actionLabel && onAction ? <button type="button" className="btn-primary state-action" onClick={onAction}>{actionLabel}</button> : actionLabel && actionTo && (
        <Link className="btn-primary state-action" to={actionTo}>
          {actionLabel}
        </Link>
      )}
    </section>
  );
}
