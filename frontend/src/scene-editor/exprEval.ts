/**
 * Safe numeric expression evaluator, a faithful port of
 * src/oled_webui/scene/expressions.py: whitelisted arithmetic, functions
 * and constants; unknown identifiers resolve from the variable scope at
 * evaluation time (t, dt, v) and raise when missing.
 */

export class SceneExprError extends Error {}

type BinOp = (a: number, b: number) => number
type Fn = (...args: number[]) => number

const BIN_OPS: Record<string, BinOp> = {
  '+': (a, b) => a + b,
  '-': (a, b) => a - b,
  '*': (a, b) => a * b,
  '/': (a, b) => {
    if (b === 0) throw new Error('Division by zero')
    return a / b
  },
  '//': (a, b) => {
    if (b === 0) throw new Error('Division by zero')
    return Math.floor(a / b)
  },
  '%': (a, b) => {
    if (b === 0) throw new Error('Division by zero')
    return a % b
  },
  '**': Math.pow,
}

const FUNCTIONS: Record<string, Fn> = {
  sin: Math.sin,
  cos: Math.cos,
  tan: Math.tan,
  abs: (x) => Math.abs(x),
  min: (...a) => Math.min(...a),
  max: (...a) => Math.max(...a),
  floor: Math.floor,
  ceil: Math.ceil,
  // Python's round(): banker's rounding (halves go to the even number).
  round: (x) => {
    const f = Math.floor(x)
    const diff = x - f
    if (diff > 0.5) return f + 1
    if (diff < 0.5) return f
    return f % 2 === 0 ? f : f + 1
  },
  sqrt: (x) => {
    if (x < 0) throw new Error('sqrt of negative number')
    return Math.sqrt(x)
  },
  clamp: (x, lo, hi) => Math.max(lo, Math.min(hi, x)),
}

export const CONSTANTS: Record<string, number> = {
  pi: Math.PI,
  tau: Math.PI * 2,
  e: Math.E,
}

/** Variables the runtime supplies to widget expressions. */
export const EXPRESSION_VARIABLES = ['t', 'dt', 'v'] as const

type Node =
  | { kind: 'num'; value: number }
  | { kind: 'name'; name: string }
  | { kind: 'bin'; op: string; left: Node; right: Node }
  | { kind: 'unary'; op: string; operand: Node }
  | { kind: 'call'; name: string; args: Node[] }

interface Token {
  type: 'num' | 'name' | 'op' | 'lparen' | 'rparen' | 'comma'
  value: string
  num?: number
}

function tokenize(source: string): Token[] {
  const tokens: Token[] = []
  let i = 0
  while (i < source.length) {
    const ch = source[i]
    if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') {
      i += 1
      continue
    }
    if (ch >= '0' && ch <= '9') {
      let j = i
      while (j < source.length && /[0-9.]/.test(source[j])) j += 1
      // exponent notation: 1e-3
      if (j < source.length && (source[j] === 'e' || source[j] === 'E')) {
        let k = j + 1
        if (k < source.length && (source[k] === '+' || source[k] === '-')) k += 1
        if (k < source.length && /[0-9]/.test(source[k])) {
          j = k
          while (j < source.length && /[0-9]/.test(source[j])) j += 1
        }
      }
      const num = Number(source.slice(i, j))
      if (!Number.isFinite(num)) {
        throw new SceneExprError(`Invalid number in expression: "${source.slice(i, j)}"`)
      }
      tokens.push({ type: 'num', value: source.slice(i, j), num })
      i = j
      continue
    }
    if (/[A-Za-z_]/.test(ch)) {
      let j = i
      while (j < source.length && /[A-Za-z0-9_]/.test(source[j])) j += 1
      tokens.push({ type: 'name', value: source.slice(i, j) })
      i = j
      continue
    }
    if (source.startsWith('**', i)) {
      tokens.push({ type: 'op', value: '**' })
      i += 2
      continue
    }
    if (source.startsWith('//', i)) {
      tokens.push({ type: 'op', value: '//' })
      i += 2
      continue
    }
    if ('+-*/%'.includes(ch)) {
      tokens.push({ type: 'op', value: ch })
      i += 1
      continue
    }
    if (ch === '(') {
      tokens.push({ type: 'lparen', value: ch })
      i += 1
      continue
    }
    if (ch === ')') {
      tokens.push({ type: 'rparen', value: ch })
      i += 1
      continue
    }
    if (ch === ',') {
      tokens.push({ type: 'comma', value: ch })
      i += 1
      continue
    }
    throw new SceneExprError(`Unexpected character "${ch}" in expression`)
  }
  return tokens
}

class Parser {
  private pos = 0

  constructor(private readonly tokens: Token[]) {}

  private peek(): Token | undefined {
    return this.tokens[this.pos]
  }

  private next(): Token {
    const token = this.tokens[this.pos]
    if (token === undefined) throw new SceneExprError('Unexpected end of expression')
    this.pos += 1
    return token
  }

  parseExpr(): Node {
    return this.parseAdd()
  }

  atEnd(): boolean {
    return this.pos >= this.tokens.length
  }

  nextToken(): Token | undefined {
    return this.tokens[this.pos]
  }

  private parseAdd(): Node {
    let left = this.parseMul()
    for (;;) {
      const token = this.peek()
      if (token?.type === 'op' && (token.value === '+' || token.value === '-')) {
        this.next()
        left = {
          kind: 'bin',
          op: token.value,
          left,
          right: this.parseMul(),
        }
      } else {
        return left
      }
    }
  }

  private parseMul(): Node {
    let left = this.parseUnary()
    for (;;) {
      const token = this.peek()
      if (
        token?.type === 'op' &&
        (token.value === '*' || token.value === '/' || token.value === '//' || token.value === '%')
      ) {
        this.next()
        left = { kind: 'bin', op: token.value, left, right: this.parseUnary() }
      } else {
        return left
      }
    }
  }

  private parseUnary(): Node {
    const token = this.peek()
    if (token?.type === 'op' && (token.value === '-' || token.value === '+')) {
      this.next()
      return { kind: 'unary', op: token.value, operand: this.parseUnary() }
    }
    return this.parsePower()
  }

  private parsePower(): Node {
    const base = this.parsePrimary()
    const token = this.peek()
    if (token?.type === 'op' && token.value === '**') {
      this.next()
      // Right-associative; the exponent may carry its own unary sign.
      return { kind: 'bin', op: '**', left: base, right: this.parseUnary() }
    }
    return base
  }

  private parsePrimary(): Node {
    const token = this.next()
    if (token.type === 'num') {
      return { kind: 'num', value: token.num ?? 0 }
    }
    if (token.type === 'lparen') {
      const inner = this.parseAdd()
      const closing = this.next()
      if (closing.type !== 'rparen') throw new SceneExprError('Missing closing parenthesis')
      return inner
    }
    if (token.type === 'name') {
      const next = this.peek()
      if (next?.type === 'lparen') {
        this.next()
        const args: Node[] = []
        if (this.peek()?.type !== 'rparen') {
          args.push(this.parseAdd())
          while (this.peek()?.type === 'comma') {
            this.next()
            args.push(this.parseAdd())
          }
        }
        const closing = this.next()
        if (closing.type !== 'rparen') throw new SceneExprError('Missing closing parenthesis')
        return { kind: 'call', name: token.value, args }
      }
      return { kind: 'name', name: token.value }
    }
    throw new SceneExprError(`Unexpected token "${token.value}" in expression`)
  }
}

function validate(node: Node): void {
  switch (node.kind) {
    case 'num':
      return
    case 'name':
      // Constants resolve at compile scope; other names must come from the
      // evaluation variables (mirrors the Python evaluator).
      return
    case 'unary':
      validate(node.operand)
      return
    case 'bin':
      if (!(node.op in BIN_OPS)) {
        throw new SceneExprError(`Disallowed operator "${node.op}"`)
      }
      validate(node.left)
      validate(node.right)
      return
    case 'call': {
      if (!(node.name in FUNCTIONS)) {
        throw new SceneExprError(
          `Only whitelisted function calls are allowed (got "${node.name}")`,
        )
      }
      for (const arg of node.args) validate(arg)
      return
    }
  }
}

/** A compiled expression: parse once, evaluate per frame. */
export class Expression {
  private readonly tree: Node
  private readonly source: string

  constructor(source: string) {
    this.source = source
    const tokens = tokenize(source)
    if (tokens.length === 0) {
      throw new SceneExprError('Empty expression')
    }
    const parser = new Parser(tokens)
    this.tree = parser.parseExpr()
    if (!parser.atEnd()) {
      throw new SceneExprError(
        `Unexpected token "${parser.nextToken()?.value}" after expression`,
      )
    }
    validate(this.tree)
  }

  evaluate(variables: Record<string, number> = {}): number {
    return this.evalNode(this.tree, { ...CONSTANTS, ...variables })
  }

  private evalNode(node: Node, scope: Record<string, number>): number {
    switch (node.kind) {
      case 'num':
        return node.value
      case 'name': {
        if (node.name in scope) return scope[node.name]!
        throw new SceneExprError(`Unknown variable "${node.name}" in "${this.source}"`)
      }
      case 'unary': {
        const value = this.evalNode(node.operand, scope)
        return node.op === '-' ? -value : value
      }
      case 'bin': {
        const left = this.evalNode(node.left, scope)
        const right = this.evalNode(node.right, scope)
        try {
          return BIN_OPS[node.op]!(left, right)
        } catch (err) {
          throw new SceneExprError(
            `${(err as Error).message} in "${this.source}"`,
          )
        }
      }
      case 'call': {
        const fn = FUNCTIONS[node.name]!
        const args = node.args.map((arg) => this.evalNode(arg, scope))
        return fn(...args)
      }
    }
  }
}

// ----------------------------------------------------------------------
// Easing curves (port of the EASINGS table).
// ----------------------------------------------------------------------

export const EASING_NAMES = [
  'linear',
  'ease-in-quad',
  'ease-out-quad',
  'ease-in-out-quad',
  'ease-in-cubic',
  'ease-out-cubic',
  'ease-in-out-cubic',
  'ease-out-back',
  'ease-out-elastic',
  'ease-out-bounce',
] as const

export type EasingName = (typeof EASING_NAMES)[number]

const EASINGS: Record<string, (t: number) => number> = {
  linear: (t) => t,
  'ease-in-quad': (t) => t * t,
  'ease-out-quad': (t) => 1 - (1 - t) * (1 - t),
  'ease-in-out-quad': (t) => (t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t)),
  'ease-in-cubic': (t) => t * t * t,
  'ease-out-cubic': (t) => 1 - (1 - t) ** 3,
  'ease-in-out-cubic': (t) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2),
  'ease-out-back': (t) => {
    const c1 = 1.70158
    const c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
  },
  'ease-out-elastic': (t) => {
    if (t === 0 || t === 1) return t
    const c4 = (2 * Math.PI) / 3
    return 2 ** (-10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1
  },
  'ease-out-bounce': (t) => {
    const n1 = 7.5625
    const d1 = 2.75
    if (t < 1 / d1) return n1 * t * t
    if (t < 2 / d1) {
      const u = t - 1.5 / d1
      return n1 * u * u + 0.75
    }
    if (t < 2.5 / d1) {
      const u = t - 2.25 / d1
      return n1 * u * u + 0.9375
    }
    const u = t - 2.625 / d1
    return n1 * u * u + 0.984375
  },
}

/** Apply a named easing curve to progress in [0, 1]. */
export function applyEasing(name: string, t: number): number {
  const curve = EASINGS[name]
  if (curve === undefined) {
    throw new SceneExprError(`Unknown easing "${name}"`)
  }
  return curve(Math.max(0, Math.min(1, t)))
}
