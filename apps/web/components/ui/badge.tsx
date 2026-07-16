import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.06em]',
  {
    variants: {
      variant: {
        default: 'border-ink bg-white text-ink',
        orange: 'border-orange/30 bg-warning-soft text-orange-dark',
        teal: 'border-teal/30 bg-success-soft text-teal',
        dark: 'border-ink bg-ink text-white',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
