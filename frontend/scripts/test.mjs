import { build } from 'esbuild'
import { spawnSync } from 'node:child_process'
import { mkdir, rm } from 'node:fs/promises'

const directory = new URL('../node_modules/.cache/offerlab-tests/', import.meta.url)
const output = new URL('latency.test.mjs', directory)
await mkdir(directory, { recursive: true })
try {
  await build({
    entryPoints: [new URL('../tests/latency.test.tsx', import.meta.url).pathname],
    outfile: output.pathname, bundle: true, packages: 'external', platform: 'node',
    format: 'esm', jsx: 'automatic',
  })
  // node:test runs registered tests on exit, without a second child-process layer.
  const result = spawnSync(process.execPath, [output.pathname], { stdio: 'inherit' })
  process.exitCode = result.status ?? 1
} finally {
  await rm(output, { force: true })
}
