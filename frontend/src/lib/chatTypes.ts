import type { UIMessage } from "ai"

export type PipelineStage = "searching" | "analyzing" | "verifying" | "saving"

export type AnswerStatus = "answered" | "insufficient_evidence" | "refused"

export type CitationData = {
  citationId: string
  chunkId: string
  documentId: string
  ticker: string
  companyName: string
  filingType: string
  filingDate: string
  fiscalYear: number
  page: number | null
  section: string | null
  sectionPath: string | null
  sourceAnchor: string | null
  provenanceKind: "page" | "anchor" | "section"
  excerpt: string
  sourceUrl: string
}

export type ChatDataParts = {
  status: { stage: PipelineStage }
  "answer-status": { status: AnswerStatus }
  citation: CitationData
}

export type ChatUIMessage = UIMessage<unknown, ChatDataParts>

export function isPipelineStage(value: unknown): value is PipelineStage {
  return value === "searching" || value === "analyzing" || value === "verifying" || value === "saving"
}
