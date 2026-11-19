import type { ChatUIMessage } from "@/lib/chatTypes"

export type ThreadSummary = {
  id: string
  title: string
  createdAt: string
  updatedAt: string
}

export type CitationSource = {
  id: string
  number: number
  documentTitle: string
  filingType?: string
  filingDate?: string
  page?: string
  section?: string
  excerpt: string
  highlightText?: string
  sourceUrl?: string
}

export type ThreadDetail = ThreadSummary & {
  messages: ChatUIMessage[]
}

export type UserSummary = {
  displayName: string
  email: string
  initials: string
  role?: string
}

export type ApiErrorBody = {
  detail?: string
  message?: string
}
