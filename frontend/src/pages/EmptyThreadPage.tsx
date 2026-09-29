export default function EmptyThreadPage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
      <h2 className="text-2xl font-semibold text-foreground">Start a conversation</h2>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        Choose an existing thread from the sidebar or create a new chat to ask questions about
        SEC filings.
      </p>
    </div>
  )
}
