import '../styles/tokens.css'
import '../styles/globals.css'
import type { Metadata } from 'next'
import { AuthProvider } from '../components/AuthProvider'
import AuthGate from '../components/AuthGate'
import { ThemeProvider } from '../components/ThemeProvider'

export const metadata: Metadata = {
  title: 'Komponist — One shared score for people and AI',
  description: 'Turn company noise into reviewed, connected context for Workrooms, live Canvas interfaces, cited presentations, and AI agents.',
  icons: {
    icon: [
      {
        url: '/brand/favicon-light.svg?v=2',
        type: 'image/svg+xml',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/brand/favicon-dark.svg?v=2',
        type: 'image/svg+xml',
        media: '(prefers-color-scheme: dark)',
      },
      { url: '/brand/favicon-32.png?v=2', type: 'image/png', sizes: '32x32' },
      { url: '/brand/favicon-16.png?v=2', type: 'image/png', sizes: '16x16' },
    ],
    shortcut: '/brand/favicon-32.png?v=2',
    apple: [{ url: '/brand/apple-touch-icon.png?v=2', type: 'image/png', sizes: '180x180' }],
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var saved=localStorage.getItem('komponist_theme');var theme=saved==='dark'||saved==='light'?saved:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=theme;document.documentElement.style.colorScheme=theme}catch(e){document.documentElement.dataset.theme='light'}})()` }} />
        <link rel="preconnect" href="https://rsms.me/" />
        <link rel="stylesheet" href="https://rsms.me/inter/inter.css" />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>
            <AuthGate>{children}</AuthGate>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
