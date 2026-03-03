import { useToast } from '../context/ToastContext'

export default function ToastContainer() {
  const { toasts, dismissToast } = useToast()

  if (toasts.length === 0) return null

  return (
    <div className="toast-container" role="region" aria-label="Notifications" aria-live="polite">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`toast toast-${toast.type}`}
          role="alert"
        >
          <span>{toast.message}</span>
          <button
            onClick={() => dismissToast(toast.id)}
            aria-label="Dismiss notification"
            title="Dismiss"
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  )
}
