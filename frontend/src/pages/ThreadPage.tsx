import { useParams } from "react-router-dom"
import { ThreadLoader } from "@/components/chat/ThreadLoader"

export default function ThreadPage() {
  const { id } = useParams<{ id: string }>()
  if (!id) return null
  return <ThreadLoader key={id} threadId={id} />
}
