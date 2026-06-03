# Xdebug

## What it is

Xdebug is a PHP debugger and profiler. It integrates with IDEs (VS Code via PHP Debug extension) to provide breakpoints, step-through execution, variable inspection, and stack traces.

## Why it must be installed explicitly

Xdebug is **not** a regular PHP extension — it ships as a `.dll` loaded via `zend_extension` in `php.ini`, not `extension`. PHP does not bundle it and package managers (WinGet, Homebrew) do not install it automatically.

### DLL compatibility

The correct `.dll` must match **all four** of:

| Factor | How to check |
|---|---|
| PHP version | `php -v` |
| Thread safety | `php -i \| findstr "Thread Safety"` |
| Compiler | `php -i \| findstr "Compiler"` |
| Architecture | `php -i \| findstr "Architecture"` |

WinGet PHP 8.4 installs as **ZTS** (Zend Thread Safe) — download the `ts` DLL from [xdebug.org/download](https://xdebug.org/download), not `nts`.

Use [xdebug.org/wizard](https://xdebug.org/wizard) — paste `php -i` output and it returns the exact `.dll` to download.

## Setup

1. Install the correct `.dll`: in my case: "PHP 8.4 TS VS17 (64 bit)" at [xdebug.org/download](https://xdebug.org/download) - Latest Versions
2. Move the DLL to the PHP `ext` directory
3. Enable in `php.ini` (in the same path of php) with `zend_extension`:
```ini
[Xdebug]
zend_extension = <path-to-dll>
```
4. Verify loaded:
```bash
php -v
# Output should include: "with Xdebug v3.x.x"
```

5. Set `xdebug.mode=debug` and `xdebug.start_with_request=yes` in `php.ini` or pass as `-d` flags at launch to enable debugging.

## Passing config at launch (without editing php.ini)

```bash
php -d xdebug.mode=debug -d xdebug.start_with_request=yes bin/console ...
```

Useful for enabling xdebug only on specific runs without affecting the global config.

## VS Code integration

Install extension **PHP Debug** (xdebug.php-debug). Add launch config:

```json
{
    "name": "Listen for Xdebug",
    "type": "php",
    "request": "launch",
    "port": 9003
}
```

Start listening in VS Code, then run the PHP process — breakpoints hit automatically.
