# PHP Code Quality

Static analysis and formatting tools for the MDG Symfony project. Currently absent — no linting or type checking enforced locally or in CI.

---

## Items

### 1. PHPStan static analysis

**What:** Add PHPStan at level 5 or above. Runs against `mdg/src/` and `mdg/tests/`. Reports type errors, unreachable code, unsafe method calls, and missing return types without executing the code.

**Why:** PHP is dynamically typed; type errors only surface at runtime today. PHPStan catches them statically — same role as `mypy` for Python. Level 5 is the minimum meaningful bar; it flags unsafe operations without requiring full annotation coverage.

**How to implement:**

1. Add to `mdg/composer.json`:
   ```json
   "require-dev": {
       "phpstan/phpstan": "^2.0",
       "phpstan/extension-installer": "^1.4",
       "phpstan/phpstan-symfony": "^2.0"
   }
   ```

2. Create `mdg/phpstan.neon`:
   ```neon
   parameters:
       level: 5
       paths:
           - src
           - tests
   ```

3. Add composer script:
   ```json
   "scripts": {
       "analyse": "phpstan analyse"
   }
   ```

4. Add step to `.github/workflows/mdg-fargate-deploy.yml` before build:
   ```yaml
   - name: Static analysis
     working-directory: mdg
     run: composer analyse
   ```

**Status:** Open

---

### 2. PHP CS Fixer formatting

**What:** Add PHP CS Fixer with a PSR-12 ruleset. Enforces consistent formatting (indentation, brace style, blank lines) across `mdg/src/` and `mdg/tests/`.

**Why:** No formatter is currently enforced. PSR-12 is the Symfony community standard. Consistent formatting reduces diff noise and eliminates style debates in review.

**How to implement:**

1. Add to `mdg/composer.json`:
   ```json
   "require-dev": {
       "friendsofphp/php-cs-fixer": "^3.0"
   }
   ```

2. Create `mdg/.php-cs-fixer.php`:
   ```php
   <?php
   $finder = PhpCsFixer\Finder::create()->in([__DIR__ . '/src', __DIR__ . '/tests']);
   return (new PhpCsFixer\Config())
       ->setRules(['@PSR12' => true])
       ->setFinder($finder);
   ```

3. Add composer scripts:
   ```json
   "scripts": {
       "cs-fix":   "php-cs-fixer fix",
       "cs-check": "php-cs-fixer fix --dry-run --diff"
   }
   ```

4. Add CI check step (dry-run only — no auto-fix in CI):
   ```yaml
   - name: Check formatting
     working-directory: mdg
     run: composer cs-check
   ```

**Status:** Open
