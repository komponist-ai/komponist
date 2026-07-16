import { BrainCircuit } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function BrandMark({ className }: { className?: string }) {
  return (
    <span className={cn('inline-grid size-9 place-items-center rounded-lg border-2 border-ink bg-orange text-white shadow-[2px_2px_0_#201c15]', className)}>
      <BrainCircuit className="size-5" strokeWidth={2.4} />
    </span>
  )
}
