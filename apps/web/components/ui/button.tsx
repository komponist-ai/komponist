import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md border-2 border-ink text-sm font-bold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'bg-orange text-white shadow-[4px_4px_0_#201c15] hover:-translate-y-0.5 hover:shadow-[6px_6px_0_#201c15] active:translate-x-1 active:translate-y-1 active:shadow-none',
        dark: 'bg-ink text-white shadow-[4px_4px_0_#e8641b] hover:-translate-y-0.5 hover:shadow-[6px_6px_0_#e8641b]',
        outline: 'bg-white text-ink shadow-[3px_3px_0_#201c15] hover:bg-paper-2 hover:-translate-y-0.5',
        ghost: 'border-transparent bg-transparent text-ink shadow-none hover:bg-paper-2',
        subtle: 'border-line bg-paper-2 text-ink shadow-none hover:border-ink',
        destructive: 'border-danger bg-danger text-white shadow-[4px_4px_0_#201c15] hover:-translate-y-0.5 hover:shadow-[6px_6px_0_#201c15] active:translate-x-1 active:translate-y-1 active:shadow-none',
      },
      size: {
        default: 'h-11 px-5',
        sm: 'h-10 px-3 text-xs',
        lg: 'h-12 px-6 text-base',
        icon: 'size-10 p-0',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  },
)
Button.displayName = 'Button'

export { Button, buttonVariants }
