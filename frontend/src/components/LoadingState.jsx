export default function LoadingState({ label = 'Carregando dados...', cards = 0 }) {
  if (cards > 0) {
    return (
      <div className="skeleton-grid" aria-label={label}>
        {Array.from({ length: cards }).map((_, index) => (
          <div className="skeleton-card" key={index}>
            <div className="skeleton-media" />
            <div className="skeleton-line is-short" />
            <div className="skeleton-line" />
            <div className="skeleton-line" />
            <div className="skeleton-footer" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="state-panel loading-panel" role="status">
      <span className="loader-dot" />
      <p>{label}</p>
    </div>
  );
}
