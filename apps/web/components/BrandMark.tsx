import { cn } from '@/lib/utils'

const K_PATH =
  'M8.2 8.1 H10.1 V11.4 L13.15 8.1 H15.6 L12.25 11.65 L15.8 15.9 H13.4 L10.9 12.75 L10.1 13.6 V15.9 H8.2 Z'

function keycapFor(size: number) {
  if (size <= 20) return { x: 3.4, y: 4.4, w: 17.2, h: 15.2, r: 4.2, sw: 2.4 }
  if (size <= 32) return { x: 3, y: 4, w: 18, h: 16, r: 4.5, sw: 1.8 }
  return { x: 2.8, y: 3.8, w: 18.4, h: 16.4, r: 4.6, sw: 1.6 }
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

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      role="img"
      aria-label={label}
      className={cn('shrink-0', className)}
    >
      {variant === 'tile' ? (
        <>
          <rect x="2.5" y="2.5" width="21.5" height="21.5" rx="6" fill="#e8641b" />
          <rect width="21.5" height="21.5" rx="6" fill="#26201b" />
          <g transform="scale(0.8958)">
            <rect
              x={keycap.x}
              y={keycap.y}
              width={keycap.w}
              height={keycap.h}
              rx={keycap.r}
              fill="none"
              stroke="#fffdf8"
              strokeWidth={keycap.sw}
            />
            <path d={K_PATH} fill="#fffdf8" />
          </g>
        </>
      ) : (
        <>
          <rect
            x={keycap.x}
            y={keycap.y}
            width={keycap.w}
            height={keycap.h}
            rx={keycap.r}
            fill="none"
            stroke="currentColor"
            strokeWidth={keycap.sw}
          />
          <path d={K_PATH} fill="currentColor" />
        </>
      )}
    </svg>
  )
}
