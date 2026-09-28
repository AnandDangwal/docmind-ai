import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

// clsx for conditional class composition, twMerge to resolve conflicting
// Tailwind classes (e.g. "px-2" vs "px-4") by keeping the last one.
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
