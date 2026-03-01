import { useEffect, useRef } from 'react'

interface Props {
  size?: number
  status?: 'active' | 'idle' | 'scheduled' | 'error'
  speed?: number // rotation speed multiplier
}

// Regular tetrahedron vertices centered at origin
const S = 1.0
const UP_VERTS: [number, number, number][] = [
  [0, -S, 0],
  [-S * 0.943, S * 0.333, -S * 0.544],
  [S * 0.943, S * 0.333, -S * 0.544],
  [0, S * 0.333, S * 1.089],
]
const DOWN_VERTS: [number, number, number][] = [
  [0, S, 0],
  [-S * 0.943, -S * 0.333, S * 0.544],
  [S * 0.943, -S * 0.333, S * 0.544],
  [0, -S * 0.333, -S * 1.089],
]
const EDGES: [number, number][] = [[0,1],[0,2],[0,3],[1,2],[2,3],[3,1]]

const STATUS_COLORS = {
  active: { up: '#6c63ff', down: '#00f0ff' },
  idle: { up: '#3a3a5c', down: '#2a3a4c' },
  scheduled: { up: '#4a4a6c', down: '#3a4a5c' },
  error: { up: '#ff6b35', down: '#ff6b35' },
}

function rotateY(p: [number, number, number], a: number): [number, number, number] {
  return [p[0]*Math.cos(a)+p[2]*Math.sin(a), p[1], -p[0]*Math.sin(a)+p[2]*Math.cos(a)]
}

function rotateX(p: [number, number, number], a: number): [number, number, number] {
  return [p[0], p[1]*Math.cos(a)-p[2]*Math.sin(a), p[1]*Math.sin(a)+p[2]*Math.cos(a)]
}

export default function MerkabaGlyph({ size = 120, status = 'active', speed = 1 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const angleRef = useRef(0)
  const rafRef = useRef<number>(undefined)

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    const ns = 'http://www.w3.org/2000/svg'
    const colors = STATUS_COLORS[status]

    // Clear previous content
    while (svg.firstChild) svg.removeChild(svg.firstChild)

    // Create elements
    const g = document.createElementNS(ns, 'g')

    const upLines = EDGES.map(() => {
      const l = document.createElementNS(ns, 'line')
      l.setAttribute('stroke', colors.up)
      l.setAttribute('stroke-width', '0.025')
      g.appendChild(l)
      return l
    })

    const downLines = EDGES.map(() => {
      const l = document.createElementNS(ns, 'line')
      l.setAttribute('stroke', colors.down)
      l.setAttribute('stroke-width', '0.025')
      g.appendChild(l)
      return l
    })

    const upDots = UP_VERTS.map(() => {
      const c = document.createElementNS(ns, 'circle')
      c.setAttribute('r', '0.04')
      c.setAttribute('fill', colors.up)
      g.appendChild(c)
      return c
    })

    const downDots = DOWN_VERTS.map(() => {
      const c = document.createElementNS(ns, 'circle')
      c.setAttribute('r', '0.04')
      c.setAttribute('fill', colors.down)
      g.appendChild(c)
      return c
    })

    svg.appendChild(g)

    const tiltX = 0.35
    const baseSpeed = 0.008

    function render() {
      angleRef.current += baseSpeed * speed
      const a = angleRef.current

      function xform(verts: [number, number, number][]) {
        return verts.map(v => rotateX(rotateY(v, a), tiltX))
      }

      const up = xform(UP_VERTS)
      const down = xform(DOWN_VERTS)

      EDGES.forEach(([ia, ib], i) => {
        upLines[i].setAttribute('x1', String(up[ia][0]))
        upLines[i].setAttribute('y1', String(up[ia][1]))
        upLines[i].setAttribute('x2', String(up[ib][0]))
        upLines[i].setAttribute('y2', String(up[ib][1]))
        upLines[i].setAttribute('stroke-opacity', String(0.4 + 0.5 * ((up[ia][2] + up[ib][2]) / 2 + 1.2) / 2.4))

        downLines[i].setAttribute('x1', String(down[ia][0]))
        downLines[i].setAttribute('y1', String(down[ia][1]))
        downLines[i].setAttribute('x2', String(down[ib][0]))
        downLines[i].setAttribute('y2', String(down[ib][1]))
        downLines[i].setAttribute('stroke-opacity', String(0.4 + 0.5 * ((down[ia][2] + down[ib][2]) / 2 + 1.2) / 2.4))
      })

      up.forEach((p, i) => { upDots[i].setAttribute('cx', String(p[0])); upDots[i].setAttribute('cy', String(p[1])) })
      down.forEach((p, i) => { downDots[i].setAttribute('cx', String(p[0])); downDots[i].setAttribute('cy', String(p[1])) })

      rafRef.current = requestAnimationFrame(render)
    }

    rafRef.current = requestAnimationFrame(render)

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [status, speed])

  return (
    <svg
      ref={svgRef}
      width={size}
      height={size}
      viewBox="-1.3 -1.3 2.6 2.6"
      className="merkaba-glyph"
    />
  )
}
