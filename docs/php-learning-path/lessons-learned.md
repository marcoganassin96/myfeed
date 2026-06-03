# Lessons Learned

---

## 1. PHP array types: native vs PHPDoc vs PHPStan

### The problem

PHP has a single `array` type that covers three conceptually different structures.
Static analyzers like PHPStan need to distinguish between them, but PHP's native type system
cannot express the difference — PHPDoc is the only way.

---

### Native PHP: one type to rule them all

In PHP, every array is a hash map. Keys can be integers or strings, in any order, with gaps.
There is no compile-time distinction between "a list of strings" and "a map of string → mixed".

```php
$a = ['a', 'b', 'c'];          // integer keys 0, 1, 2
$b = ['name' => 'Marco'];      // string keys
$c = [0 => 'a', 5 => 'b'];     // integer keys, non-contiguous
```

All three are the same type in PHP: `array`.

---

### PHPDoc / PHPStan types

PHPStan introduces typed array syntax in PHPDoc. These are **not valid PHP syntax** — they
only exist in comments and are parsed by the static analyzer.

#### `array<TKey, TValue>`
The general form. Declares key type and value type explicitly.

```php
/** @var array<string, mixed> $row */   // string keys, any values (DB row)
/** @var array<int, string> $ids */     // integer keys, string values
```

Note: `array<int, string>` does **not** guarantee contiguous keys or starting at 0.
Keys `[0 => 'a', 5 => 'b']` satisfy `array<int, string>`.

#### `array<TValue>` (one-argument shorthand)
Shorthand — omits the key type. PHPStan expands this to `array<array-key, TValue>`.

```php
/** @var array<string> $names */
// equivalent to:
/** @var array<array-key, string> $names */
```

#### `array-key`
PHPStan built-in alias for `string|int`. Matches any array key, whether string or integer.

```php
/** @var array<array-key, mixed> $data */   // accepts any array
```

Use `array<array-key, T>` when a function must accept both associative arrays and
indexed arrays (e.g. a generic cache `set()` that stores both single rows and row lists).

#### `T[]` (bracket shorthand)
The `T[]` notation is widely used across PHP ecosystem tools (PHPDoc, PHPStorm, PHPStan).
It is equivalent to `array<array-key, T>` — same meaning, shorter syntax.

```php
/** @var string[] $names */
// equivalent to:
/** @var array<array-key, string> $names */
// equivalent to:
/** @var array<string> $names */
```

All three forms are identical to PHPStan. Use `string[]` when communicating to developers
unfamiliar with PHPStan generic syntax — it is universally recognized in the PHP ecosystem.

#### `list<TValue>` — PHPDoc only, does not exist in PHP runtime
A `list<T>` is a special PHPStan subtype meaning:
- integer keys only
- keys start at 0
- keys are contiguous (no gaps): 0, 1, 2, 3 …
- value type is `T`

```php
/** @var list<string> $chunks */   // [0 => 'a', 1 => 'b', 2 => 'c']
```

`list<T>` is a strict subtype of `array<int, T>`, which is a strict subtype of `array<array-key, T>`:

```
list<string>  ⊂  array<int, string>  ⊂  array<array-key, string>  ⊂  array
```

**There is no `list<T>` in PHP runtime.** PHP has no concept of "contiguous starting-at-zero array".
You can have `[0 => 'a', 1 => 'b']` and then do `unset($arr[0])` and PHP happily gives you
`[1 => 'b']` — broken list, valid PHP array. PHPStan only enforces the `list` contract
statically; at runtime there is no enforcement.

---

### Variadic parameters `...$keys`

A variadic parameter like `string ...$keys` captures all extra arguments into an array.

```php
function delete(string ...$keys): void { ... }
delete('a', 'b', 'c');
// $keys = [0 => 'a', 1 => 'b', 2 => 'c']
```

**PHP runtime:** always creates a 0-indexed contiguous array — equivalent to `list<string>`.

**PHPStan inference:** infers `array<int|string, string>` conservatively. Reason: PHP does not
prevent a caller from passing a named argument, which would use a string key:

```php
delete(first: 'a', second: 'b');   // keys are now 'first', 'second' — string keys
```

Because PHPStan cannot rule out named arguments at call sites, it conservatively widens the
key type to `int|string`. This means `...$keys` fails to satisfy `array<int, string>` directly.

#### Ergonomic advantage: single value or collection, same signature

A variadic parameter accepts both naturally — no overloading, no array wrapping:

```php
public function delete(string ...$keys): void { ... }

// single key
$cache->delete('newsletter:42');

// multiple keys
$cache->delete('newsletter:42', 'newsletter:43', 'newsletter:44');

// spread an existing array
$ids = ['newsletter:42', 'newsletter:43'];
$cache->delete(...$ids);
```

---

### Summary table

| PHPDoc type | Keys | Contiguous? | Runtime equivalent |
|---|---|---|---|
| `array` | any | any | plain `array` |
| `string[]` / `T[]` | string or int | any | any array (= `array<array-key, T>`) |
| `array<string, mixed>` | string only | any | associative array |
| `array<int, string>` | int only | not required | indexed, may have gaps |
| `array<array-key, T>` | string or int | any | any array |
| `list<T>` | int, 0-based | required | `array_values($arr)` result |
| `...$keys` inferred | `int\|string` (conservative) | not guaranteed | always `list` at runtime |
