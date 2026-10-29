import { Check, Circle, LoaderCircle, X } from "lucide-react"
import type { PipelineStage } from "@/lib/chatTypes"

const STAGES: Array<{ id: PipelineStage; label: string }> = [
  { id: "searching", label: "Searching filings" },
  { id: "analyzing", label: "Analyzing evidence and drafting" },
  { id: "verifying", label: "Verifying citations" },
  { id: "saving", label: "Saving verified answer" },
]

export function ProgressChecklist({
  currentStage,
  failed,
}: {
  currentStage: PipelineStage
  failed: boolean
}) {
  const currentIndex = STAGES.findIndex((stage) => stage.id === currentStage)

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`Assistant progress: ${STAGES[currentIndex].label}${failed ? " failed" : ""}`}
      className="mx-6 mb-2 rounded-lg border border-border bg-muted/40 px-4 py-3"
    >
      <p className="mb-2 text-xs font-medium text-foreground">Working on your question</p>
      <ol className="grid gap-1.5 text-xs">
        {STAGES.map((stage, index) => {
          const isActive = index === currentIndex
          const isComplete = index < currentIndex
          const isFailed = failed && isActive
          const Icon = isFailed ? X : isComplete ? Check : isActive ? LoaderCircle : Circle

          return (
            <li
              key={stage.id}
              className={`flex items-center gap-2 ${
                isFailed
                  ? "text-destructive"
                  : isComplete || isActive
                    ? "text-foreground"
                    : "text-muted-foreground"
              }`}
            >
              <Icon
                className={`size-3.5 shrink-0 ${isActive && !isFailed ? "animate-spin" : ""}`}
                aria-hidden="true"
              />
              <span>{stage.label}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
