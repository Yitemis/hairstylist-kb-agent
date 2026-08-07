/**用户长期记忆 API。*/
import { request } from './client'

export interface UserFact {
  fact_key: string
  fact_value: string
  confidence: number
  created_at: string
  updated_at: string
}

export async function listUserFacts(): Promise<UserFact[]> {
  const r = await request<{ facts: UserFact[] }>('/api/user/facts')
  return r.data?.facts || []
}

export async function deleteUserFact(factKey: string): Promise<void> {
  await request(`/api/user/facts/${factKey}`, { method: 'DELETE' })
}

export async function extractUserFacts(): Promise<{ count: number }> {
  const r = await request<{ count: number }>('/api/user/facts/extract', { method: 'POST' })
  return r.data
}
