import { Node } from '@tiptap/core'
import { ReactNodeViewRenderer } from '@tiptap/react'
import MediaBlock from './MediaEmbed'

export const MediaEmbed = Node.create({
  name: 'mediaEmbed',
  group: 'block',
  atom: true,
  selectable: true,
  addAttributes() {
    return {
      assetId: { default: null, parseHTML: element => element.getAttribute('data-asset-id'), renderHTML: attributes => ({ 'data-asset-id': attributes.assetId }) },
      caption: { default: '', parseHTML: element => element.getAttribute('data-caption') || '', renderHTML: attributes => ({ 'data-caption': attributes.caption }) },
    }
  },
  parseHTML() { return [{ tag: 'div[data-type="media-embed"]' }] },
  renderHTML({ HTMLAttributes }) { return ['div', { ...HTMLAttributes, 'data-type': 'media-embed' }] },
  addNodeView() { return ReactNodeViewRenderer(MediaBlock) },
})
