export default function Card({ title, extra, children, className = "" }) {
  return (
    <div className={`card ${className}`}>
      {(title || extra) && (
        <div className="card-head">
          {title && <h3 className="card-title">{title}</h3>}
          {extra && <div className="card-extra">{extra}</div>}
        </div>
      )}
      <div className="card-body">{children}</div>
    </div>
  );
}
