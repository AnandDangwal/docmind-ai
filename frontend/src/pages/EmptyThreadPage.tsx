export default function EmptyThreadPage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
      <h2 className="text-2xl font-semibold text-foreground">Start a conversation</h2>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        Create a new chat or choose a conversation from the sidebar. Verified answers will show
        the filing metadata used as evidence.
      </p>
    </div>
  )
}
