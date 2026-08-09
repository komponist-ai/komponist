import { cn } from '@/lib/utils'

// Brown tile is 21.5x21.5 at origin, orange shadow offset 2.5 right/down
// Keycap centered with equal 3.25 margin on all sides: 21.5 - 2*3.25 = 15
const KEYCAP = { x: 3.25, y: 3.25, w: 15, h: 15, r: 4, sw: 1.6 }

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
  // Center of brown tile for text positioning
  const brownCenter = 21.5 / 2

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
          <rect
            x={KEYCAP.x}
            y={KEYCAP.y}
            width={KEYCAP.w}
            height={KEYCAP.h}
            rx={KEYCAP.r}
            fill="none"
            stroke="#fffdf8"
            strokeWidth={KEYCAP.sw}
          />
          <text
            x={brownCenter}
            y="14.5"
            textAnchor="middle"
            fill="#fffdf8"
            fontFamily="Arial Rounded MT Bold, Avenir Next Rounded, Nunito, sans-serif"
            fontSize="11"
            fontWeight="bold"
          >
            K
          </text>
        </>
      ) : (
        <>
          <rect
            x={KEYCAP.x}
            y={KEYCAP.y}
            width={KEYCAP.w}
            height={KEYCAP.h}
            rx={KEYCAP.r}
            fill="none"
            stroke="currentColor"
            strokeWidth={KEYCAP.sw}
          />
          <text
            x={brownCenter}
            y="14.5"
            textAnchor="middle"
            fill="currentColor"
            fontFamily="Arial Rounded MT Bold, Avenir Next Rounded, Nunito, sans-serif"
            fontSize="11"
            fontWeight="bold"
          >
            K
          </text>
        </>
      )}
    </svg>
  )
}
