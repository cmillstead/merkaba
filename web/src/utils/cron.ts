export function parseCronField(field: string, max: number): number[] {
  if (field === '*') {
    return Array.from({ length: max }, (_, i) => i)
  }
  if (field.startsWith('*/')) {
    const step = parseInt(field.slice(2), 10)
    if (isNaN(step) || step <= 0) return []
    const result: number[] = []
    for (let i = 0; i < max; i += step) result.push(i)
    return result
  }

  // Handle comma-separated list: 1,3,5
  if (field.includes(',')) {
    const result: number[] = []
    for (const part of field.split(',')) {
      const parsed = parseCronField(part.trim(), max)
      result.push(...parsed)
    }
    return [...new Set(result)].sort((a, b) => a - b)
  }

  // Handle range: 1-5 or 1-5/2
  if (field.includes('-')) {
    const [rangePart, stepPart] = field.split('/')
    const [startStr, endStr] = rangePart.split('-')
    const start = parseInt(startStr, 10)
    const end = parseInt(endStr, 10)
    const step = stepPart ? parseInt(stepPart, 10) : 1

    if (isNaN(start) || isNaN(end) || isNaN(step) || step <= 0) return []
    if (start < 0 || end >= max || start > end) return []

    const result: number[] = []
    for (let i = start; i <= end; i += step) result.push(i)
    return result
  }

  const n = parseInt(field, 10)
  if (isNaN(n) || n < 0 || n >= max) return []
  return [n]
}

export function cronOccurrences(cronExpr: string, start: Date, end: Date): Date[] {
  let expr = cronExpr.trim()

  // Handle cron aliases
  const aliases: Record<string, string> = {
    '@yearly': '0 0 1 1 *',
    '@annually': '0 0 1 1 *',
    '@monthly': '0 0 1 * *',
    '@weekly': '0 0 * * 0',
    '@daily': '0 0 * * *',
    '@midnight': '0 0 * * *',
    '@hourly': '0 * * * *',
  }

  if (expr.startsWith('@')) {
    expr = aliases[expr] || expr
  }

  const parts = expr.split(/\s+/)
  if (parts.length !== 5) return []

  const minutes = parseCronField(parts[0], 60)
  const hours = parseCronField(parts[1], 24)
  const doms = parseCronField(parts[2], 32) // 0-31, but we'll filter valid days
  const months = parseCronField(parts[3], 13) // 0-12, but cron months are 1-12
  const dows = parseCronField(parts[4], 7)   // 0=Sun through 6=Sat

  if (!minutes.length || !hours.length) return []

  const domIsWild = parts[2] === '*'
  const dowIsWild = parts[4] === '*'
  const monthIsWild = parts[3] === '*'

  const results: Date[] = []
  const cursor = new Date(start)
  cursor.setSeconds(0, 0)

  while (cursor <= end) {
    const month1 = cursor.getMonth() + 1
    const dom = cursor.getDate()
    const dow = cursor.getDay()

    if (monthIsWild || months.includes(month1)) {
      const domMatch = domIsWild || doms.includes(dom)
      const dowMatch = dowIsWild || dows.includes(dow)

      // Standard cron: if both DOM and DOW are restricted, match either (OR).
      // If only one is restricted, match that one.
      const dayMatch = (domIsWild && dowIsWild) ||
        (domIsWild && dowMatch) ||
        (dowIsWild && domMatch) ||
        (!domIsWild && !dowIsWild && (domMatch || dowMatch))

      if (dayMatch) {
        for (const h of hours) {
          for (const m of minutes) {
            const candidate = new Date(cursor)
            candidate.setHours(h, m, 0, 0)
            if (candidate >= start && candidate <= end) {
              results.push(candidate)
            }
          }
        }
      }
    }

    cursor.setDate(cursor.getDate() + 1)
    cursor.setHours(0, 0, 0, 0)
  }

  return results
}
