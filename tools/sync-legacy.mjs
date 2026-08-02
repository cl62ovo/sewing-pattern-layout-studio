import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const publicRoot = path.join(repositoryRoot, 'apps', 'web', 'public')
const legacyRoot = path.join(publicRoot, 'legacy')

await rm(legacyRoot, { force: true, recursive: true })
await mkdir(legacyRoot, { recursive: true })
const legacyHtml = await readFile(path.join(repositoryRoot, 'index.html'), 'utf8')
const sanitizedHtml = legacyHtml
  .replace(
    /\s*<script>\s*\(function\(\)\{function c\(\).*?challenge-platform.*?<\/script>/s,
    '',
  )
  .replaceAll('href="assets/', 'href="/assets/')
  .replaceAll('href="favicon.svg"', 'href="/legacy/favicon.svg"')
  .replaceAll(
    'https://sewing-pattern-layout-studio.liminfei080602.chatgpt.site/favicon.svg',
    '/legacy/favicon.svg',
  )
await writeFile(path.join(legacyRoot, 'index.html'), sanitizedHtml, 'utf8')
await cp(path.join(repositoryRoot, 'favicon.svg'), path.join(legacyRoot, 'favicon.svg'))
await cp(path.join(repositoryRoot, 'assets'), path.join(legacyRoot, 'assets'), {
  recursive: true,
})

// The legacy Vinext runtime preloads some hashed files from absolute /assets URLs.
await mkdir(path.join(publicRoot, 'assets'), { recursive: true })
await cp(path.join(repositoryRoot, 'assets'), path.join(publicRoot, 'assets'), {
  force: true,
  recursive: true,
})

console.log('Legacy Nest & Cut build synced to apps/web/public/legacy')