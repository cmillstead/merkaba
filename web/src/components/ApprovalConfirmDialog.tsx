import { useCallback, useEffect, useId, useRef, useState } from 'react'

export type ApprovalAction = 'approve' | 'reject'

interface Props {
  open: boolean
  action: ApprovalAction
  itemDescription: string
  requireTotp: boolean
  submitting?: boolean
  onConfirm: (totp?: string) => void
  onCancel: () => void
}

const ACTION_LABELS: Record<ApprovalAction, { title: string; confirmLabel: string; btnClass: string }> = {
  approve: { title: 'Approve', confirmLabel: 'Confirm Approve', btnClass: 'btn-green' },
  reject: { title: 'Reject', confirmLabel: 'Confirm Reject', btnClass: 'btn-red' },
}

export default function ApprovalConfirmDialog({
  open,
  action,
  itemDescription,
  requireTotp,
  submitting = false,
  onConfirm,
  onCancel,
}: Props) {
  const [totpCode, setTotpCode] = useState('')
  const totpInputRef = useRef<HTMLInputElement>(null)
  const confirmBtnRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  // Reset TOTP when dialog opens/closes
  useEffect(() => {
    if (open) {
      setTotpCode('')
    }
  }, [open])

  // Focus management: auto-focus TOTP input or Confirm button when dialog opens
  useEffect(() => {
    if (!open) return
    // Small delay to ensure DOM is rendered
    const timer = setTimeout(() => {
      if (requireTotp && totpInputRef.current) {
        totpInputRef.current.focus()
      } else if (confirmBtnRef.current) {
        confirmBtnRef.current.focus()
      }
    }, 50)
    return () => clearTimeout(timer)
  }, [open, requireTotp])

  // Escape key closes dialog
  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCancel()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onCancel])

  // Trap focus within dialog
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !dialogRef.current) return
    const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
      'input, button:not([disabled])'
    )
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }, [])

  const handleConfirm = useCallback(() => {
    onConfirm(totpCode || undefined)
  }, [onConfirm, totpCode])

  if (!open) return null

  const { title, confirmLabel, btnClass } = ACTION_LABELS[action]

  return (
    <div
      className="approval-dialog-overlay"
      onClick={onCancel}
    >
      <div
        ref={dialogRef}
        className="approval-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={e => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <h3 id={titleId} className="approval-dialog-title">
          {title} this action?
        </h3>

        <p className="approval-dialog-description">
          {itemDescription}
        </p>

        {requireTotp && (
          <div className="approval-dialog-totp">
            <label
              htmlFor="approval-totp-input"
              className="approval-dialog-totp-label"
            >
              TOTP Code (required if 2FA is enabled)
            </label>
            <input
              ref={totpInputRef}
              id="approval-totp-input"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6-digit code"
              value={totpCode}
              onChange={e => setTotpCode(e.target.value)}
              className="approval-dialog-totp-input"
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  handleConfirm()
                }
              }}
            />
          </div>
        )}

        <div className="approval-dialog-actions">
          <button
            ref={confirmBtnRef}
            className={`btn ${btnClass}`}
            onClick={handleConfirm}
            disabled={submitting}
          >
            {submitting ? 'Submitting...' : confirmLabel}
          </button>
          <button
            className="btn btn-dim"
            onClick={onCancel}
            disabled={submitting}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
