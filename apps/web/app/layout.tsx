import '../styles/tokens.css'
import '../styles/globals.css'
import type { Metadata } from 'next'
import { AuthProvider } from '../components/AuthProvider'
import AuthGate from '../components/AuthGate'

export const metadata: Metadata = {
  title: 'Komponist — The programmable company brain',
  description: 'Company context, composed for every agent. Turn scattered company knowledge into governed context that humans and AI agents can use.',
  icons: {
    icon: '/icon.svg',
    shortcut: '/icon.svg',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://rsms.me/" />
        <link rel="stylesheet" href="https://rsms.me/inter/inter.css" />
      </head>
      <body>
        <AuthProvider>
          <AuthGate>{children}</AuthGate>
        </AuthProvider>
      </body>
    </html>
  )
}
