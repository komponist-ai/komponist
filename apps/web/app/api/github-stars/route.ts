import { NextResponse } from 'next/server'

const REPOSITORY_ENDPOINT = 'https://api.github.com/repos/komponist-ai/komponist'

export const revalidate = 900

export async function GET() {
  const headers: HeadersInit = {
    Accept: 'application/vnd.github+json',
    'User-Agent': 'komponist-web',
    'X-GitHub-Api-Version': '2022-11-28',
  }

  if (process.env.GITHUB_TOKEN) {
    headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`
  }

  try {
    const response = await fetch(REPOSITORY_ENDPOINT, {
      headers,
      next: { revalidate },
    })

    if (!response.ok) {
      return NextResponse.json(
        { stars: 0, available: false },
        { headers: { 'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=3600' } },
      )
    }

    const repository = await response.json() as { stargazers_count?: number }
    const stars = Number.isFinite(repository.stargazers_count)
      ? Number(repository.stargazers_count)
      : 0

    return NextResponse.json(
      { stars, available: true },
      { headers: { 'Cache-Control': 'public, s-maxage=900, stale-while-revalidate=86400' } },
    )
  } catch {
    return NextResponse.json(
      { stars: 0, available: false },
      { headers: { 'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=300' } },
    )
  }
}
