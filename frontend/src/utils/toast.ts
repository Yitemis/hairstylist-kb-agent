export type ToastType = 'success' | 'error' | 'info'

export interface ToastEvent {
  id: number
  message: string
  type: ToastType
}

let listeners: ((toasts: ToastEvent[]) => void)[] = []
let toasts: ToastEvent[] = []
let nextId = 1

function notify() {
  listeners.forEach(l => l([...toasts]))
}

export function showToast(message: string, type: ToastType = 'info') {
  const id = nextId++
  toasts.push({ id, message, type })
  notify()
  // 自动移除
  setTimeout(() => {
    toasts = toasts.filter(t => t.id !== id)
    notify()
  }, 3000)
}

export function successToast(message: string) {
  showToast(message, 'success')
}

export function errorToast(message: string) {
  showToast(message, 'error')
}

export function infoToast(message: string) {
  showToast(message, 'info')
}

export function subscribeToasts(listener: (toasts: ToastEvent[]) => void) {
  listeners.push(listener)
  listener(toasts)
  return () => {
    listeners = listeners.filter(l => l !== listener)
  }
}
