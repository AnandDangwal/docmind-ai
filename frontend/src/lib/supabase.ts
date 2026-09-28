import { createClient } from "@supabase/supabase-js"
import { env } from "@/lib/env"

// Single browser client (anon key only). Owns the auth session: persisted in
// localStorage and refreshed automatically, so everything else reads the
// current token from here instead of passing it around.
export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})
