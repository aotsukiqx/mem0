export type Category = "personal identity" | "relationships" | "health & wellness" | "career & work" | "education & learning" | 
  "hobbies & interests" | "entertainment" | "food & dining" | "travel & places" | 
  "finance & money" | "shopping & purchases" | "organization & planning" | "communication" |
  "technology & digital" | "legal & compliance" | "business & professional" | "support & services" |
  "news & current events" | "knowledge & facts" | "feedback & reviews" | "goals & aspirations"
export type Client = "chrome" | "chatgpt" | "cursor" | "windsurf" | "terminal" | "api"

export interface Memory {
  id: string
  memory: string
  metadata: any
  client: Client
  categories: Category[]
  created_at: number
  app_name: string
  state: "active" | "paused" | "archived" | "deleted"
}