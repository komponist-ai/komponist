import Image from 'next/image'
import { cn } from '@/lib/utils'

export default function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn('inline-flex size-9 shrink-0 overflow-hidden rounded-lg shadow-[2px_2px_0_#e8641b]', className)}
      aria-label="Komponist"
      role="img"
    >
      <Image src="/brand/favicon-dark.svg" width={36} height={36} className="size-full" alt="" aria-hidden="true" priority />
    </span>
  )
}
