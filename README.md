# QuickCalc

A tiny calculator that lives in the Windows system tray, appears on a global hotkey
(`Ctrl+Alt+C`), takes typed maths the way you'd write it, and gets out of the way again.
Built for electronics work: SI prefixes, engineering notation, hex/binary, units and
mil ↔ mm conversions.

```
2(3+4)              = 14            4.7k || 10k        = 3197
9 V / 4.7 kohm      = 1.915 mA      10 mil to mm       = 0.254 mm
72 F to C           = 22.22 °C      0xFF + 0b1010      = 265
1/(2 pi * 1 kohm * 100 nF) = 1.592 kHz                 255 to hex = 0xFF
```

(Shown at 4 significant figures; the default is 10.)

No installer, no admin rights, no network access, no telemetry, no update checks.

## Run from source

Needs Python 3.11 or newer on Windows.

```
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m quickcalc
```

`python -m quickcalc --tray` starts hidden in the tray; `--quit` closes the running copy.
Use `pythonw` instead of `python` to run without a console window.

Run the tests (engine and settings only, no Qt needed):

```
.venv\Scripts\python -m pytest
```

## Build the portable exe

```
.venv\Scripts\python build.py
```

This produces `dist\QuickCalc\` (about 65 MB). Copy that folder anywhere under your user
profile and run `QuickCalc.exe`. To remove it: quit from the tray, delete the folder, and
optionally delete `%APPDATA%\QuickCalc`.

## Using it

| Key | Action |
|---|---|
| `Ctrl+Alt+C` (global) | Show / hide the window on the monitor under the mouse |
| `Enter` | Commit: add to history, copy the result to the clipboard |
| `Esc` | Hide |
| `Up` / `Down` | Cycle through earlier inputs |
| `Ctrl+B` | Show / hide the button keypad |
| `Ctrl+H` | Show / hide history |
| `Ctrl+L` | Clear history |
| `Ctrl+,` | Settings |

The result preview updates as you type; half-typed input just shows nothing. Click a
history row to put it back in the input; right-click for copy / insert / clear. Drag the
title strip to move the window. A missing `)` at the end of a line is forgiven.

The tray icon menu has Show, Settings, Start with Windows and Quit. Launching QuickCalc
again while it is running simply shows the running copy.

### Changing the hotkey

Tray icon → **Settings…** → click the **Global hotkey** box and press the new combination
(at least one of Ctrl / Alt / Shift / Win plus a key, or a bare function key). You can
also edit `"hotkey"` in `%APPDATA%\QuickCalc\settings.json` while QuickCalc is closed, e.g.
`"Ctrl+Shift+Space"`. If Windows refuses the combination because another program owns
it, a tray notification says so and the previous hotkey stays active.

The hotkey uses Win32 `RegisterHotKey`; there is no keyboard hook.

### Calculator key (optional, built exe only)

Settings → **Open QuickCalc with the keyboard's Calculator key** writes one per-user
registry value:

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\AppKey\18
    ShellExecute = <path to QuickCalc.exe>
```

To undo it, untick the box, or delete the key by hand:

```
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\AppKey\18" /f
```

After that the key opens Windows Calculator again. If you move the QuickCalc folder,
untick and re-tick the option. The option is disabled when running from source because
the override can only hold a single program path.

"Start with Windows" likewise uses only `HKCU\...\CurrentVersion\Run` (value `QuickCalc`).

## Syntax

### Operators, loosest to tightest

| Operator | Meaning |
|---|---|
| `name = expr` | assign a variable (session only) |
| `to`, `in`, `->` | convert the whole line: `5 in + 1 ft to mm` |
| `\|` | bitwise or |
| `xor` | bitwise xor |
| `&` | bitwise and |
| `<<` `>>` | shifts |
| `+` `-` | add, subtract |
| `*` `/` `mod` `%` | multiply, divide, modulo |
| `\|\|` | parallel: `a*b/(a+b)` |
| `-x` `+x` `~x` | negate, bitwise not |
| *adjacency* | implicit multiplication: `2pi`, `2(3+4)`, `9 V`, `(1+2)(3+4)` |
| `^` `**` | power, right-associative: `2^3^2` = 512, `-2^2` = -4 |
| `x%` | percent |

Two consequences worth knowing:

- **Implicit multiplication binds tighter than `*` and `/`.** `9 V / 4.7 kohm` is
  9 V ÷ (4.7 kΩ) and `1/2pi` is 1/(2π). Write `(1/2) pi` if you mean the other thing.
- **`||` binds tighter than `*` and `/`**, so `9 / 4.7k || 10k` divides by the parallel pair
  and `r1 + r2 || r3` is `r1 + (r2 || r3)`.

`^` is always power; use `xor` for exclusive-or. `~` follows two's-complement rules
(`~5` = -6); mask it if you want a fixed width: `~5 & 0xFF`. Bitwise operators need whole
numbers. Unicode `× ÷ − · π √ ² ³ → µ Ω °` are understood.

### `ans` and leading operators

`ans` is the last result. A line that starts with `*  /  +  ^  ||  &  |  <<  >>  xor  mod`
or with `to` / `in` / `->` is applied to `ans`: after `265`, typing `*2` gives 530 and
`to hex` gives `0x109`. A leading `-` is **not** applied to `ans`, so `-5 + 3` is still −2;
type `ans - 5` for that.

### Percent

- `a + b%` and `a - b%` add or subtract *b percent of a*: `200 + 10%` → 220, `200 - 10%` → 180.
- Anywhere else `b%` is just `b/100`: `80 * 15%` → 12, `15%` → 0.15, `200 / 50%` → 400.
- `%` followed by a number, name or `(` is modulo instead: `10 % 3` → 1. (`mod` always works.)

### Numbers

`0xFF`, `0b1010`, `0o17`, `1e-6`, `1_000_000`, `.5`.

### SI prefixes on numbers

A single prefix letter directly after a number, with no space, scales it:

| `f` | `p` | `n` | `u` / `µ` | `m` | `k` | `M` | `G` | `T` |
|---|---|---|---|---|---|---|---|---|
| 1e-15 | 1e-12 | 1e-9 | 1e-6 | 1e-3 | 1e3 | 1e6 | 1e9 | 1e12 |

`4.7k` → 4700, `100n` → 1e-7, `10M` → 10 000 000. Lowercase `m` is milli, capital `M` is mega.

Three of those letters are also unit symbols (`m` metre, `G` gauss, `T` tesla). The rule:

1. **With a space it is always the unit**: `10 m` is ten metres.
2. **Glued, with no other units on the line, it is the prefix**: `10m` → 0.01, `3.3 / 10m` → 330.
3. **Glued, with other units or a unit conversion on the line, it is the unit**:
   `10m to ft`, `10m/s`, `3m + 20cm`.
4. If the chosen reading produces a unit mismatch, the other one is tried before giving up.

Longer symbols are never ambiguous: `10mm`, `4.7kohm`, `10mA`, `100nF` are units, and
`100n F` is 100 nF. A glued prefix letter wins over a variable of the same name, so avoid
naming variables `k`, `m`, `u`…

### Functions and constants

`sqrt cbrt abs round floor ceil log ln log2 exp sin cos tan asin acos atan atan2 min max`,
plus `pi`, `e`. `log` is base 10 (`log(8, 2)` for another base); `round(x, 2)` rounds to
two decimals. Trig uses radians or degrees according to Settings; an explicit unit always
wins: `sin(30 deg)`, `sin(30°)`.

### Units

Units come from [Pint](https://pint.readthedocs.io), so most things you'd expect work:
`m mm um in ft yd mi mil thou`, `g kg lb oz`, `s ms min h day`, `L mL gal floz cup`,
`V A ohm Ω F H W J Hz S`, `N lbf Pa psi bar atm`, `mph kph knot`, `deg rad`, `rpm`,
`B kB MB GB KiB MiB GiB bit kb Mb Mbps`, `sqft sqin acre ha`, `cal kcal BTU kWh Wh mAh eV`,
`dBm`, and any SI prefix on any SI unit.

- **Convert** with `to`, `in` or `->`: `60 mph to km/h`, `1 GiB in MB`, `10 mil -> mm`.
  A conversion applies to the whole line and can't sit inside parentheses.
- **Arithmetic keeps units**, and results are tidied to a sensible named unit:
  `9 V / 4.7 kohm` → mA, `60 mph * 2 h` → 120 mi, `1/(1 kHz)` → 1 ms, `500 mA * 2 h` → 1 Ah.
- **`in` is inch or the keyword.** It is the conversion keyword only when something comes
  before it and a plain unit follows it; otherwise it is the inch. So `5 in in mm`,
  `5 in to mm`, `5 mm in in` and `5 in * 2` all do what they look like.
- **Temperature**: `72 F to C`, `100 C to K`, `72 degF to degC`, `72 °F to °C`. `F` and `C`
  normally mean farad and coulomb (`100n F`, `1 C / 1 s`); they are read as °F / °C when
  the farad/coulomb reading would be a unit mismatch, which is exactly what happens in a
  temperature conversion. `degF` / `degC` are never ambiguous. `20 degC + 5 degC` → 25 °C.
- **Compound input**: `5 ft 3 in to cm` → 160.02 cm, `1 h 30 min to s`.
- **Bases**: `255 to hex`, `0x3F to bin`, `42 to oct`, `0xFF to dec`.
- **dBm**: `20 dBm to mW` → 100 mW, `100 mW to dBm` → 20 dBm. dB values can be converted
  but not added or scaled directly.
- Bare `k`, `u`, `M`, `R`, `a` are *not* units (Pint defines them as physical constants,
  which would turn typos into nonsense); `c` is the speed of light: `c / 2.4 GHz to cm`.
- A variable with the same name as a unit shadows the unit for the session.

### Custom units

`%APPDATA%\QuickCalc\units.txt` is created on first run with commented examples
(Settings → **Edit custom units…** opens it). One Pint definition per line:

```
oz_cu = 1.37 * thou          # copper weight: 2 oz_cu to mm -> 0.069596 mm
rack_unit = 1.75 * inch = RU
```

Restart QuickCalc after editing. A line that can't be read is skipped and reported in a
tray notification; it never stops the app from starting.

## Output formatting

Set in Settings; the default is **Auto** with 10 significant figures.

| Mode | `3.3 / 4.7k` | `9 V / 4.7 kohm` |
|---|---|---|
| Auto | `0.0007021276596` | `1.914893617 mA` |
| Engineering / SI | `702.1276596 µ` | `1.914893617 mA` |
| Scientific | `7.021276596e-4` | `1.914893617e-3 A` |
| Fixed (4) | `0.0007` | `0.0019 A` |

- Auto shows plain decimals between 1e-4 and 1e12 and engineering exponents
  (`12.34e-6`) outside that range. Whole numbers are shown exactly.
- In Auto and Engineering modes, SI units get the prefix that puts the number between
  1 and 1000 (`0.5 V` → `500 mV`). A unit you asked for with `to` is never changed
  (`10 mil to mm` → `0.254 mm`). Seconds are not scaled above 1 s, grams not above kg,
  metres not above km.
- Float noise is rounded away at the chosen precision: `0.1 + 0.2` → `0.3`.
- Optional: thousands separators, and hex + binary shown under whole-number results.
  The clipboard always gets the number without separators.

## Files

Everything QuickCalc writes is in `%APPDATA%\QuickCalc`:

| File | Contents |
|---|---|
| `settings.json` | all settings |
| `history.json` | up to 500 history entries (if "Remember history" is on) |
| `units.txt` | your custom units |

## Project layout

```
quickcalc/
  engine/        parser, units, evaluation, formatting. No Qt imports.
    lexer.py  parser.py  evaluator.py  units.py  formatter.py  engine.py  errors.py
  config.py      settings and history files
  winplatform.py hotkey parsing and the HKCU registry entries
  gui/           PySide6: window, keypad, settings dialog, tray, hotkey, single instance
tests/           pytest suite for the engine, config and hotkey parsing
build.py         PyInstaller build
```

The engine can be used on its own:

```python
from quickcalc.engine import Engine
engine = Engine()
engine.evaluate("9 V / 4.7 kohm").text   # '1.914893617 mA'
```

Input is parsed by a hand-written tokenizer and recursive-descent parser; `eval()` is
never used.

## Known limits

- Conversions can't be nested in parentheses: write `5 in * 2 to mm`, not `(5 in to mm) * 2`.
- Tesla ↔ gauss doesn't convert (Pint keeps Gaussian units in a separate system).
- Variables and `ans` last until you quit; only the history is saved.
- Arithmetic is ordinary double precision, displayed to at most 15 significant figures.
