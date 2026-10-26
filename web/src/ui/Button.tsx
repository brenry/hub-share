import type { ButtonHTMLAttributes, ReactNode, Ref } from 'react'
import { Icon, type IconName } from './Icon'
import { cx } from './cx'
import s from './Button.module.css'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'ghost' | 'danger'
  small?: boolean
  icon?: IconName
  children?: ReactNode
  ref?: Ref<HTMLButtonElement>
}

/** Buttons are 2rem high; `small` is 1.5rem. An icon-only button needs an aria-label. */
export function Button({ variant = 'default', small = false, icon, children, className, type = 'button', ...rest }: Props) {
  const cls = cx(s.btn, variant !== 'default' && s[variant], small && s.small, children === undefined && s.square, className)
  return (
    <button type={type} className={cls} {...rest}>
      {icon && <Icon name={icon} small={small} />}
      {children}
    </button>
  )
}
