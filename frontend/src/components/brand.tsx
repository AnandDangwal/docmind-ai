import { cn } from "@/lib/utils"

export function AppIcon({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-white",
        className,
      )}
    >
      <img
        alt=""
        aria-hidden="true"
        className="size-full scale-[1.85] object-cover contrast-[1.2] brightness-[1.08] saturate-[1.05] select-none"
        draggable={false}
        src="/app_icon.jpg"
      />
    </span>
  )
}

type BrandProps = {
  compact?: boolean
  onIconClick?: () => void
  iconLabel?: string
}

export function Brand({
  compact = false,
  onIconClick,
  iconLabel = "Toggle sidebar",
}: BrandProps) {
  const icon = <AppIcon className="size-8" />

  return (
    <div
      className="flex items-center gap-2.5 text-sm font-semibold tracking-tight text-foreground"
      aria-label="Document Copilot"
    >
      {onIconClick ? (
        <button
          type="button"
          className="rounded-lg border-0 bg-transparent p-0 transition-opacity hover:opacity-75 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={onIconClick}
          aria-label={iconLabel}
          title={iconLabel}
        >
          {icon}
        </button>
      ) : (
        icon
      )}

      {!compact && (
        <span className="whitespace-nowrap">Document Copilot</span>
      )}
    </div>
  )
}
