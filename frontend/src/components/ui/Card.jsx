/**
 * Card — glass-panel container with optional title + footer.
 */
export default function Card({ title, footer, className = '', children, actions }) {
  return (
    <div className={`glass-card rounded-xl p-4 ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between mb-3">
          {title && <h3 className="text-white font-bold text-sm">{title}</h3>}
          {actions && <div className="flex gap-2">{actions}</div>}
        </div>
      )}
      <div>{children}</div>
      {footer && <div className="mt-3 pt-3 border-t border-white/10 text-white/60 text-xs">{footer}</div>}
    </div>
  )
}
