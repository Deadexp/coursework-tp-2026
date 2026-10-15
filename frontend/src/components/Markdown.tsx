import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Теория уроков хранится в Markdown; сырой HTML не отображается. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}
