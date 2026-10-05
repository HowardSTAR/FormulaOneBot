// Top-layer listbox: the iframe uses the same branded interaction as the site.
export function trackPicker(trigger: HTMLButtonElement, items: {id: string; name: string}[]) {
  const menu = document.createElement('div')
  menu.id = 'track-options'
  menu.className = 'track-options'
  menu.setAttribute('popover', 'auto')
  menu.setAttribute('role', 'listbox')
  menu.setAttribute('aria-label', 'Трассы')
  trigger.setAttribute('aria-controls', menu.id)
  document.body.append(menu)
  const close = () => { menu.hidePopover(); trigger.setAttribute('aria-expanded', 'false'); trigger.focus() }
  const options = items.map(item => {
    const option = document.createElement('button')
    option.type = 'button'
    option.value = item.id
    option.textContent = item.name
    option.setAttribute('role', 'option')
    option.tabIndex = -1
    option.addEventListener('click', () => {
      setValue(item.id)
      close()
      trigger.dispatchEvent(new Event('change'))
    })
    menu.append(option)
    return option
  })
  function setValue(id: string) {
    trigger.value = id
    trigger.textContent = `${items.find(item => item.id === id)?.name ?? 'Выбрать трассу'} ▾`
    options.forEach(option => option.setAttribute('aria-selected', String(option.value === id)))
  }
  function open() {
    if (trigger.disabled) return
    const rect = trigger.getBoundingClientRect()
    const height = Math.min(280, Math.max(rect.top, innerHeight - rect.bottom) - 12)
    Object.assign(menu.style, {width: `${rect.width}px`, left: `${rect.left}px`, maxHeight: `${height}px`,
      top: innerHeight - rect.bottom >= height ? `${rect.bottom + 4}px` : 'auto',
      bottom: innerHeight - rect.bottom >= height ? 'auto' : `${innerHeight - rect.top + 4}px`})
    menu.showPopover()
    trigger.setAttribute('aria-expanded', 'true')
    options.find(option => option.value === trigger.value)?.focus()
  }
  trigger.addEventListener('click', () => menu.matches(':popover-open') ? close() : open())
  trigger.addEventListener('keydown', event => {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) { event.preventDefault(); open() }
  })
  menu.addEventListener('toggle', () => trigger.setAttribute('aria-expanded', String(menu.matches(':popover-open'))))
  let typed = '', typedAt = 0
  menu.addEventListener('keydown', event => {
    event.stopPropagation()
    const current = options.indexOf(document.activeElement as HTMLButtonElement)
    let next = current
    if (event.key === 'Escape') { event.preventDefault(); close(); return }
    if (event.key === 'Tab') { menu.hidePopover(); trigger.focus(); return }
    if (event.key === 'ArrowDown') next = (current + 1) % options.length
    else if (event.key === 'ArrowUp') next = (current - 1 + options.length) % options.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = options.length - 1
    else if (event.key.length === 1 && event.key !== ' ' && !event.ctrlKey && !event.metaKey) {
      typed = Date.now() - typedAt > 700 ? event.key : typed + event.key
      typedAt = Date.now()
      next = options.findIndex(option => option.textContent?.toLowerCase().startsWith(typed.toLowerCase()))
    } else return
    event.preventDefault()
    options[next]?.focus()
  })
  menu.addEventListener('keyup', event => event.stopPropagation())
  window.addEventListener('resize', () => menu.hidePopover())
  return {setValue}
}
