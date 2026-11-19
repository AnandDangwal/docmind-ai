import type { User } from "@supabase/supabase-js"

import type { UserSummary } from "@/lib/types"

export function summarizeUser(user: User): UserSummary {
  const email = user.email ?? ""
  const metadataName = typeof user.user_metadata.full_name === "string" ? user.user_metadata.full_name.trim() : ""
  const emailName = email.split("@")[0]?.replace(/[._-]+/g, " ") ?? "Analyst"
  const displayName = metadataName || emailName.replace(/\b\w/g, (letter) => letter.toUpperCase())
  const initials = displayName
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("")

  return {
    displayName,
    email,
    initials: initials || "DC",
    role: typeof user.user_metadata.role === "string" ? user.user_metadata.role : undefined,
  }
}
