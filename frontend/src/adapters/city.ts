import { DEFAULT_CITY, resolveCity } from '../core/cities'

const STORAGE_KEY = 'ew.city'

export function getCity(available: readonly string[]): string {
  try {
    return resolveCity(localStorage.getItem(STORAGE_KEY), available)
  } catch {
    return DEFAULT_CITY
  }
}

export function setCity(value: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    /* 写不进去就只用内存态 */
  }
}
