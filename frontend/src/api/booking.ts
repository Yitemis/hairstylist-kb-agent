/**预约 API：分店 / 发型师 / 服务 / 订单 / 时段。*/
import { request } from './client'

export interface Branch {
  id: number
  name: string
  address: string
  phone?: string
  description?: string
  latitude?: number | null
  longitude?: number | null
  max_daily_appointments?: number
  is_active: boolean
}

export async function listBranchesNearby(lat: number, lng: number): Promise<Branch[]> {
  const r = await request<Branch[]>(`/api/branches/nearby?lat=${lat}&lng=${lng}`)
  return r.data || []
}

export async function listBranches(): Promise<Branch[]> {
  const r = await request<Branch[]>('/api/branches')
  return r.data || []
}

export interface Stylist {
  id: number
  branch_id: number
  name: string
  avatar?: string | null
  specialties: string[]
  description?: string | null
  max_daily_hours?: number
  is_active: boolean
}

export async function listStylists(branchId?: number): Promise<Stylist[]> {
  const url = branchId ? `/api/stylists?branch_id=${branchId}` : '/api/stylists'
  const r = await request<Stylist[]>(url)
  return r.data || []
}

export interface Service {
  id: number
  name: string
  category: string
  description?: string | null
  duration_minutes: number
  price?: number | null
  is_active: boolean
}

export async function listServices(): Promise<Service[]> {
  const r = await request<Service[]>('/api/services')
  return r.data || []
}

export interface OrderCreate {
  branch_id: number
  stylist_id?: number
  service_id?: number
  service_type?: string
  appointment_date: string
  appointment_time: string
  duration_minutes?: number
  total_price?: number
  customer_phone: string
  customer_name: string
  note?: string
}

export interface Order {
  id: number
  order_no: string
  user_id: number
  branch_id: number
  customer_name: string
  customer_phone: string
  stylist_id?: number
  service_id?: number
  service_type: string
  appointment_date: string
  appointment_time: string
  status: string
  total_price?: number
  note?: string
  created_at: string
}

export async function createOrder(body: OrderCreate): Promise<any> {
  const r = await request<Order>('/api/orders', {
    method: 'POST', body: JSON.stringify(body),
  })
  return r
}

export async function listMyOrders(status?: string): Promise<Order[]> {
  const url = status ? `/api/orders?status=${status}` : '/api/orders'
  const r = await request<Order[]>(url)
  return r.data || []
}

export async function getOrderDetail(orderId: number): Promise<Order | null> {
  const r = await request<Order>(`/api/orders/${orderId}`)
  return r.data || null
}

export async function cancelMyOrder(orderId: number) {
  return request(`/api/orders/${orderId}/cancel`, { method: 'POST' })
}

export interface AvailableSlot {
  time: string
  available: boolean
  stylist_id: number
}

export async function getAvailableSlots(
  branchId: number, stylistId: number, date: string,
): Promise<AvailableSlot[]> {
  const r = await request<AvailableSlot[]>(
    `/api/orders/available-slots?branch_id=${branchId}&stylist_id=${stylistId}&date=${date}`,
  )
  return r.data || []
}
