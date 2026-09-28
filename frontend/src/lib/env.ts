// Only module allowed to read import.meta.env. Throws at import time so a
// misconfigured build fails on boot instead of on the first request.
// Each var is read with a static property access so Vite can inline it.

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`Missing required env var ${name} (see frontend/.env.example)`)
  }
  return value
}

function requiredUrl(name: string, value: string | undefined): string {
  const url = required(name, value)
  if (!URL.canParse(url)) throw new Error(`${name} must be an absolute URL, got "${url}"`)
  return url.replace(/\/+$/, "")
}

// The anon key ships to every browser; a service-role key here would bypass RLS.
function requiredAnonKey(name: string, value: string | undefined): string {
  const key = required(name, value)
  if (key.startsWith("sb_secret_") || jwtRole(key) === "service_role") {
    throw new Error(`${name} is a service-role/secret key; use the anon (public) key`)
  }
  return key
}

function jwtRole(token: string): unknown {
  const payload = token.split(".")[1]
  if (!payload) return undefined
  try {
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"))
    return (JSON.parse(json) as { role?: unknown }).role
  } catch {
    return undefined
  }
}

export const env = {
  apiBaseUrl: requiredUrl("VITE_API_BASE_URL", import.meta.env.VITE_API_BASE_URL),
  supabaseUrl: requiredUrl("VITE_SUPABASE_URL", import.meta.env.VITE_SUPABASE_URL),
  supabaseAnonKey: requiredAnonKey("VITE_SUPABASE_ANON_KEY", import.meta.env.VITE_SUPABASE_ANON_KEY),
} as const
