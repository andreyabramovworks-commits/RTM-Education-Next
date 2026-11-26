import { createElement } from 'react'
import { Node } from '@tiptap/core'
import { ReactNodeViewRenderer } from '@tiptap/react'
import GoogleBlock from './GoogleBlock'

export function googleEmbedNodes(articleId: string) {
  return (['google_document', 'google_spreadsheet'] as const).map(name => Node.create({
    name, group: 'block', atom: true, selectable: true,
    addAttributes() {
      return { fileId: { default: null }, sourceUrl: { default: null }, snapshot: { default: null } }
    },
    parseHTML() { return [{ tag: `div[data-type="${name}"]` }] },
    renderHTML({ HTMLAttributes }) { return ['div', { ...HTMLAttributes, 'data-type': name }] },
    addNodeView() { return ReactNodeViewRenderer(props => createElement(GoogleBlock, { ...props, articleId })) },
  }))
}
