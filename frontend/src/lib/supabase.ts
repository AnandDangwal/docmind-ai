import { createClient } from "@supabase/supabase-js"

import { env } from "@/lib/env"

export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})

export async function getAccessToken(): Promise<string> {
  const { data, error } = await supabase.auth.getSession()

  if (error) {
    throw error
  }

  if (!data.session?.access_token) {
    throw new Error("Your session has expired. Sign in again to continue.")
  }

  return data.session.access_token
}
