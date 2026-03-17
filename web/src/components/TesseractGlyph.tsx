import { useEffect, useRef, useState } from 'react'

interface Props {
  size?: number
  status?: 'active' | 'idle' | 'scheduled' | 'error'
  speed?: number
}

// 16 vertices of a tesseract: all combinations of (±1, ±1, ±1, ±1)
const VERTS: [number, number, number, number][] = []
for (let i = 0; i < 16; i++) {
  VERTS.push([
    (i & 1) ? 1 : -1,
    (i & 2) ? 1 : -1,
    (i & 4) ? 1 : -1,
    (i & 8) ? 1 : -1,
  ])
}

// 32 edges: connect vertices differing in exactly one coordinate
const EDGES: [number, number][] = []
for (let i = 0; i < 16; i++) {
  for (let j = i + 1; j < 16; j++) {
    let diff = 0
    for (let k = 0; k < 4; k++) {
      if (VERTS[i][k] !== VERTS[j][k]) diff++
    }
    if (diff === 1) EDGES.push([i, j])
  }
}

// Edge type by w-coordinate: inner cube (w=-1), outer cube (w=+1), cross-edges
type EdgeType = 'inner' | 'outer' | 'cross'
function getEdgeType(ia: number, ib: number): EdgeType {
  const wa = VERTS[ia][3], wb = VERTS[ib][3]
  if (wa === -1 && wb === -1) return 'inner'
  if (wa === 1 && wb === 1) return 'outer'
  return 'cross'
}

const STATUS_COLORS = {
  active: { inner: '#6c63ff', outer: '#00f0ff', cross: '#8855dd' },
  idle: { inner: '#6a6a8c', outer: '#5a6a7c', cross: '#606080' },
  scheduled: { inner: '#707092', outer: '#607080', cross: '#687088' },
  error: { inner: '#ff6b35', outer: '#ff6b35', cross: '#ff6b35' },
}

function rotate4(v: number[], a: number, b: number, angle: number): number[] {
  const out = [...v]
  const c = Math.cos(angle)
  const s = Math.sin(angle)
  out[a] = v[a] * c - v[b] * s
  out[b] = v[a] * s + v[b] * c
  return out
}

function project4to3(v: number[], d4: number): [number, number, number] {
  const w = 1 / (d4 - v[3])
  return [v[0] * w, v[1] * w, v[2] * w]
}

function project3to2(v: [number, number, number], d3: number): [number, number, number] {
  const w = 1 / (d3 - v[2])
  return [v[0] * w, v[1] * w, v[2]]
}

interface GlyphElements {
  backGroup: SVGGElement
  orbGroup: SVGGElement
  frontGroup: SVGGElement
  orbCircle: SVGCircleElement
  edges: Array<{ line: SVGLineElement; type: EdgeType; ia: number; ib: number }>
  dots: Array<{ circle: SVGCircleElement; idx: number }>
}

const D4 = 2.5   // 4D camera distance
const D3 = 5.0   // 3D camera distance
const SCALE = 4.8

export default function TesseractGlyph({ size = 120, status = 'active', speed = 1 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const angleRef = useRef(0)
  const rafRef = useRef<number | undefined>(undefined)
  const elementsRef = useRef<GlyphElements | null>(null)
  const prevSizeRef = useRef<number | undefined>(undefined)

  const [reducedMotion, setReducedMotion] = useState(() =>
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false
  )

  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)')
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    const ns = 'http://www.w3.org/2000/svg'
    const colors = STATUS_COLORS[status]
    const id = svg.id || `tg-${Math.random().toString(36).slice(2, 8)}`
    svg.id = id

    const sizeChanged = prevSizeRef.current !== size
    if (sizeChanged || !elementsRef.current) {
      while (svg.firstChild) svg.removeChild(svg.firstChild)

      const defs = document.createElementNS(ns, 'defs')
      const orbGrad = document.createElementNS(ns, 'radialGradient')
      orbGrad.id = `${id}-orb`
      const stops: [string, string][] = [
        ['0%',   'rgba(230,220,255,1)'],
        ['8%',   'rgba(180,160,255,0.95)'],
        ['20%',  'rgba(140,120,245,0.7)'],
        ['38%',  'rgba(90,70,210,0.4)'],
        ['60%',  'rgba(50,38,150,0.15)'],
        ['100%', 'rgba(25,20,80,0.0)'],
      ]
      stops.forEach(([off, col]) => {
        const st = document.createElementNS(ns, 'stop')
        st.setAttribute('offset', off)
        st.setAttribute('stop-color', col)
        orbGrad.appendChild(st)
      })
      defs.appendChild(orbGrad)
      svg.appendChild(defs)

      const backGroup = document.createElementNS(ns, 'g')
      const orbGroup = document.createElementNS(ns, 'g')
      const frontGroup = document.createElementNS(ns, 'g')
      svg.appendChild(backGroup)
      svg.appendChild(orbGroup)
      svg.appendChild(frontGroup)

      const orbCircle = document.createElementNS(ns, 'circle')
      orbCircle.setAttribute('cx', '0')
      orbCircle.setAttribute('cy', '0')
      orbCircle.setAttribute('r', '0.6')
      orbCircle.setAttribute('fill', `url(#${id}-orb)`)
      orbGroup.appendChild(orbCircle)

      const isSmall = size < 200
      const strokeWidth = isSmall ? '0.035' : '0.02'
      const dotRadius = isSmall ? '0.05' : '0.035'

      const edges: GlyphElements['edges'] = EDGES.map(([ia, ib]) => {
        const line = document.createElementNS(ns, 'line')
        const type = getEdgeType(ia, ib)
        line.setAttribute('stroke', colors[type])
        line.setAttribute('stroke-width', strokeWidth)
        line.setAttribute('stroke-linecap', 'round')
        return { line, ia, ib, type }
      })

      const dots: GlyphElements['dots'] = VERTS.map((_, idx) => {
        const circle = document.createElementNS(ns, 'circle')
        circle.setAttribute('r', dotRadius)
        const w = VERTS[idx][3]
        circle.setAttribute('fill', w === -1 ? colors.inner : colors.outer)
        return { circle, idx }
      })

      elementsRef.current = { backGroup, orbGroup, frontGroup, orbCircle, edges, dots }
      prevSizeRef.current = size
    } else {
      const { edges, dots } = elementsRef.current
      edges.forEach(e => {
        e.line.setAttribute('stroke', colors[e.type])
      })
      dots.forEach(d => {
        const w = VERTS[d.idx][3]
        d.circle.setAttribute('fill', w === -1 ? colors.inner : colors.outer)
      })
    }
  }, [size, status])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    const baseSpeed = 0.006

    function drawFrame(animate: boolean) {
      const els = elementsRef.current
      if (!els) {
        if (animate) rafRef.current = requestAnimationFrame(() => drawFrame(true))
        return
      }

      if (animate) angleRef.current += baseSpeed * speed
      const a = angleRef.current

      const projected = VERTS.map(v => {
        let r = rotate4(v, 0, 3, a)           // XW rotation — the "tesseract fold"
        r = rotate4(r, 1, 2, a * 0.6)         // YZ rotation
        r = rotate4(r, 0, 2, a * 0.3)         // XZ gentle tilt
        const p3 = project4to3(r, D4)
        const [x, y, z] = project3to2(p3, D3)
        return [x * SCALE, y * SCALE, z] as [number, number, number]
      })

      const { backGroup, frontGroup, orbCircle, edges, dots } = els

      while (backGroup.firstChild) backGroup.removeChild(backGroup.firstChild)
      while (frontGroup.firstChild) frontGroup.removeChild(frontGroup.firstChild)

      edges.forEach(e => {
        const pa = projected[e.ia]
        const pb = projected[e.ib]
        const avgZ = (pa[2] + pb[2]) / 2
        const opacity = Math.max(0.1, Math.min(1, 0.25 + 0.6 * ((avgZ + 1.5) / 3.0)))

        e.line.setAttribute('x1', String(pa[0]))
        e.line.setAttribute('y1', String(pa[1]))
        e.line.setAttribute('x2', String(pb[0]))
        e.line.setAttribute('y2', String(pb[1]))
        e.line.setAttribute('stroke-opacity', String(opacity));

        (avgZ > 0 ? frontGroup : backGroup).appendChild(e.line)
      })

      dots.forEach(d => {
        const p = projected[d.idx]
        d.circle.setAttribute('cx', String(p[0]))
        d.circle.setAttribute('cy', String(p[1]))
        const opacity = Math.max(0.15, Math.min(1, 0.3 + 0.7 * ((p[2] + 1.5) / 3.0)))
        d.circle.setAttribute('fill-opacity', String(opacity));

        (p[2] > 0 ? frontGroup : backGroup).appendChild(d.circle)
      })

      const pulse = reducedMotion ? 0.75 : 0.75 + 0.1 * Math.sin(a * 2.5)
      orbCircle.setAttribute('r', String(pulse))

      if (animate) rafRef.current = requestAnimationFrame(() => drawFrame(true))
    }

    if (rafRef.current !== undefined) cancelAnimationFrame(rafRef.current)

    if (reducedMotion) {
      drawFrame(false)
    } else {
      rafRef.current = requestAnimationFrame(() => drawFrame(true))
    }

    return () => {
      if (rafRef.current !== undefined) cancelAnimationFrame(rafRef.current)
    }
  }, [speed, reducedMotion])

  return (
    <svg
      ref={svgRef}
      width={size}
      height={size}
      viewBox="-1.6 -1.6 3.2 3.2"
      className="tesseract-glyph"
    />
  )
}
