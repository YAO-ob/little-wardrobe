import { DEFAULT_CITY, resolveCity, type CityName } from '../core/cities'

const STORAGE_KEY = 'ew.city'

export function getCity(): CityName {
  try {
    return resolveCity(localStorage.getItem(STORAGE_KEY))
  } catch {
    return DEFAULT_CITY
  }
}

export function setCity(value: CityName): void {
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    /* 写不进去就只用内存态 */
  }
}
