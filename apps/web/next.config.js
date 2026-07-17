/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone', // Required for Docker deployment
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'www.notion.so', pathname: '/images/logo-ios.png' },
      { protocol: 'https', hostname: 'a.slack-edge.com', pathname: '/80588/marketing/img/meta/slack_hash_256.png' },
      { protocol: 'https', hostname: 'www.gstatic.com', pathname: '/images/branding/productlogos/drive_2026/v2/web-64dp/logo_drive_2026_color_2x_web_64dp.png' },
    ],
  },
  env: {
    API_URL: process.env.API_URL || 'http://localhost:8000',
  },
}

module.exports = nextConfig
