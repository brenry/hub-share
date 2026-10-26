// HocusPocus Desktop, when the page runs inside it. The client names itself in `navigator.userAgent`
// ("HocusPocusDesktop/<version>", then "tags=2,3" when instances carry tags); a page opening `hpd:instance/<tag>`
// gets the instance with that tag, and one opening a saved instance's address gets that instance.

const TAG = /HocusPocusDesktop\//
const TAGS = /HocusPocusDesktop\/\S+ tags=([\d,]+)/

/** Whether the page runs inside the client. */
export const insideDesktop = (ua: string = navigator.userAgent): boolean => TAG.test(ua)

/** The tags the client's instances carry, ascending; empty outside the client or when none is tagged. */
export const desktopTags = (ua: string = navigator.userAgent): number[] =>
  (TAGS.exec(ua)?.[1] ?? '').split(',').map(Number).filter(n => Number.isInteger(n) && n > 0).sort((a, b) => a - b)

/** What a bar's monitor button offers: the client's tagged instances (`hpd:instance/<n>`), or the Hub's own
 *  instance when none is tagged (the client opens a saved instance when a page asks for its address). */
export const launchTargets = (ua: string = navigator.userAgent): { label: string; url: string }[] => {
  const tags = desktopTags(ua)
  return tags.length ? tags.map(n => ({ label: String(n), url: `hpd:instance/${n}` })) : [{ label: 'Hub', url: `${location.origin}/` }]
}
