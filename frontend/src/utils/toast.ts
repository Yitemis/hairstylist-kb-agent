type ToastType = 'success' | 'error' | 'info'

interface ToastEvent {
  id: string
  type: ToastType
  message: string
}

type Listener = (toasts: ToastEvent[]) => void

let toasts: ToastEvent[] = []
const listeners: Set<Listener> = new Set()

function notify() {
  listeners.forEach(l => l([...toasts]))
}

export function showToast(message: string, type: ToastType = 'info') {
  const id = Math.random().toString(36).slice(2)
  toasts = [...toasts, { id, type, message }]
  notify()
  setTimeout(() => {
    toasts = toasts.filter(t => t.id !== id)
    notify()
  }, 3200)
}

export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export type { ToastEvent, ToastType }
