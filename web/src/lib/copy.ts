/** Copy when the page is a secure context; on plain-HTTP LAN pages, select the field instead. */
export async function copyOrSelect(text: string, field: HTMLInputElement | null): Promise<'copied' | 'selected'> {
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return 'copied'
    } catch {
      // Fall through to selecting the text.
    }
  }
  field?.focus({ preventScroll: true })
  field?.select()
  return 'selected'
}
