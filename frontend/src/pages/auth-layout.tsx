import { Link, Outlet } from "react-router-dom"

import { Brand } from "@/components/brand"

export function AuthLayout() {
  return (
    <main className="grid min-h-svh min-w-0 grid-rows-[auto_1fr_auto] overflow-x-hidden bg-[radial-gradient(circle_at_50%_35%,#fafafa_0,#fff_52%)] px-5 py-6 sm:px-9 sm:py-8">
      <header>
        <Link to="/login" aria-label="Document Copilot sign in">
          <Brand />
        </Link>
      </header>
      <div className="grid min-w-0 place-items-center py-10">
        <div className="w-full min-w-0 max-w-[410px] rounded-xl bg-background p-1 sm:border sm:border-border sm:p-9 sm:shadow-[0_18px_55px_rgba(0,0,0,0.055)]">
          <Outlet />
        </div>
      </div>
      <footer className="text-center text-[11px] text-muted-foreground">Grounded answers from the firm&apos;s SEC filing corpus.</footer>
    </main>
  )
}
