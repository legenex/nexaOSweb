# nexaOSweb desktop

Tauri v2 wrapper that loads the built `apps/web` and ships as a Mac dmg and a Windows msi.

## Develop

```bash
pnpm --filter desktop dev
```

This runs `tauri dev`, which starts the web dev server (`pnpm --filter web dev`) and opens
a frameless window pointing at it. The window reaches the local Brain on port 8847.

## Build

```bash
pnpm --filter desktop build
```

## Secrets

The desktop never bundles the bearer token. It is read from the OS secure store (Keychain
on macOS, Credential Manager on Windows) through the keyring crate. Seed it once with the
`set_bearer` command, or with the platform credential tool under service `nexaosweb`,
account `desktop-bearer`.

## Icons

Generate the icon set before the first release build:

```bash
pnpm --filter desktop tauri icon path/to/source.png
```

This writes `src-tauri/icons/` referenced by `tauri.conf.json`.
