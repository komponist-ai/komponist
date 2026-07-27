import { cn } from '@/lib/utils'

const K_PATH =
  'M8.2 8.1 H10.1 V11.4 L13.15 8.1 H15.6 L12.25 11.65 L15.8 15.9 H13.4 L10.9 12.75 L10.1 13.6 V15.9 H8.2 Z'

function keycapFor(size: number) {
  if (size <= 20) return { x: 3.4, y: 4.4, width: 17.2, height: 15.2, radius: 4.2, stroke: 2.4 }
  if (size <= 32) return { x: 3, y: 4, width: 18, height: 16, radius: 4.5, stroke: 1.8 }
  return { x: 2.8, y: 3.8, width: 18.4, height: 16.4, radius: 4.6, stroke: 1.6 }
}

export default function BrandMark({
  size = 36,
  variant = 'tile',
  className,
  label = 'Komponist',
}: {
  size?: number
  variant?: 'tile' | 'mark'
  className?: string
  label?: string
}) {
  const keycap = keycapFor(size)
  const color = variant === 'tile' ? '#fffdf8' : 'currentColor'

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      role="img"
      aria-label={label}
      className={cn('shrink-0', className)}
    >
      {variant === 'tile' && (
        <rect width="24" height="24" rx="6" fill="#201c15" />
      )}
      <rect
        x={keycap.x}
        y={keycap.y}
        width={keycap.width}
        height={keycap.height}
        rx={keycap.radius}
        fill="none"
        stroke={color}
        strokeWidth={keycap.stroke}
      />
      <path d={K_PATH} fill={color} />
    </svg>
  )
}
