import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a rating to 2 decimal places
 */
export function formatRating(rating: number | null | undefined): string {
  if (rating == null || rating === 0) {
    return "0.00";
  }
  return rating.toFixed(2);
}
