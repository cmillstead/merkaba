import { useEffect, useRef, useState } from 'react'

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
  idle: { up: '#6a6a8c', down: '#5a6a7c' },
  scheduled: { up: '#707092', down: '#607080' },
  error: { up: '#ff6b35', down: '#ff6b35' },
}

function rotateY(p: [number, number, number], a: number): [number, number, number] {
  return [p[0]*Math.cos(a)+p[2]*Math.sin(a), p[1], -p[0]*Math.sin(a)+p[2]*Math.cos(a)]
}

function rotateX(p: [number, number, number], a: number): [number, number, number] {
  return [p[0], p[1]*Math.cos(a)-p[2]*Math.sin(a), p[1]*Math.sin(a)+p[2]*Math.cos(a)]
}

interface GlyphElements {
  backGroup: SVGGElement
  orbGroup: SVGGElement
  frontGroup: SVGGElement
  orbCircle: SVGCircleElement
  edges: Array<{ poly: SVGPolygonElement; type: 'up' | 'down'; ia: number; ib: number }>
  dots: Array<{ circle: SVGCircleElement; type: 'up' | 'down'; idx: number }>
}

export default function MerkabaGlyphV2({ size = 120, status = 'active', speed = 1 }: Props) {
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
    const id = svg.id || `mg2-${Math.random().toString(36).slice(2, 8)}`
    svg.id = id

    const sizeChanged = prevSizeRef.current !== size
    if (sizeChanged || !elementsRef.current) {
      while (svg.firstChild) svg.removeChild(svg.firstChild)

      const defs = document.createElementNS(ns, 'defs')

      // Bright orb gradient — opaque center, soft transparent edge
      const orbGrad = document.createElementNS(ns, 'radialGradient')
      orbGrad.id = `${id}-orb`
      ;([
        ['0%',   'rgba(230,220,255,1)'],
        ['4%',   'rgba(190,170,255,1)'],
        ['10%',  'rgba(140,120,240,0.95)'],
        ['20%',  'rgba(80,60,180,0.85)'],
        ['35%',  'rgba(40,30,100,0.65)'],
        ['55%',  'rgba(16,14,40,0.35)'],
        ['100%', 'rgba(10,10,20,0)'],
      ] as [string, string][]).forEach(([off, col]) => {
        const st = document.createElementNS(ns, 'stop')
        st.setAttribute('offset', off)
        st.setAttribute('stop-color', col)
        orbGrad.appendChild(st)
      })
      defs.appendChild(orbGrad)
      svg.appendChild(defs)

      // Layer order: back edges → orb → front edges
      const backGroup = document.createElementNS(ns, 'g')
      svg.appendChild(backGroup)

      const orbGroup = document.createElementNS(ns, 'g')
      svg.appendChild(orbGroup)
      const orbCircle = document.createElementNS(ns, 'circle')
      orbCircle.setAttribute('cx', '0')
      orbCircle.setAttribute('cy', '0')
      orbCircle.setAttribute('r', '0.9')
      orbCircle.setAttribute('fill', `url(#${id}-orb)`)
      orbGroup.appendChild(orbCircle)

      const frontGroup = document.createElementNS(ns, 'g')
      svg.appendChild(frontGroup)

      // Tapered edges — polygons instead of lines
      const edges: GlyphElements['edges'] = []
      EDGES.forEach(([ia, ib]) => {
        const p = document.createElementNS(ns, 'polygon')
        p.setAttribute('fill', colors.up)
        edges.push({ poly: p, type: 'up', ia, ib })
      })
      EDGES.forEach(([ia, ib]) => {
        const p = document.createElementNS(ns, 'polygon')
        p.setAttribute('fill', colors.down)
        edges.push({ poly: p, type: 'down', ia, ib })
      })

      // Vertex dots — size/opacity vary with depth
      const dots: GlyphElements['dots'] = []
      UP_VERTS.forEach((_, i) => {
        const c = document.createElementNS(ns, 'circle')
        c.setAttribute('fill', colors.up)
        dots.push({ circle: c, type: 'up', idx: i })
      })
      DOWN_VERTS.forEach((_, i) => {
        const c = document.createElementNS(ns, 'circle')
        c.setAttribute('fill', colors.down)
        dots.push({ circle: c, type: 'down', idx: i })
      })

      elementsRef.current = { backGroup, orbGroup, frontGroup, orbCircle, edges, dots }
      prevSizeRef.current = size
    } else {
      const { edges, dots } = elementsRef.current
      edges.forEach(e => {
        e.poly.setAttribute('fill', e.type === 'up' ? colors.up : colors.down)
      })
      dots.forEach(d => {
        d.circle.setAttribute('fill', d.type === 'up' ? colors.up : colors.down)
      })
    }
  }, [size, status])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    const tiltX = 0.35
    const baseSpeed = 0.008

    function drawFrame(animate: boolean) {
      const els = elementsRef.current
      if (!els) {
        if (animate) rafRef.current = requestAnimationFrame(() => drawFrame(true))
        return
      }

      if (animate) angleRef.current += baseSpeed * speed
      const a = angleRef.current

      // Counter-rotating tetrahedra
      const up = UP_VERTS.map(v => rotateX(rotateY(v, -a), tiltX))
      const down = DOWN_VERTS.map(v => rotateX(rotateY(v, a), tiltX))
      const { backGroup, frontGroup, orbCircle, edges, dots } = els

      while (backGroup.firstChild) backGroup.removeChild(backGroup.firstChild)
      while (frontGroup.firstChild) frontGroup.removeChild(frontGroup.firstChild)

      // Tapered edges — polygon quads with depth-based width
      edges.forEach(e => {
        const verts = e.type === 'up' ? up : down
        const pa = verts[e.ia], pb = verts[e.ib]
        const avgZ = (pa[2] + pb[2]) / 2
        const opacity = 0.4 + 0.5 * (avgZ + 1.2) / 2.4

        const depthA = (pa[2] + 1.2) / 2.4
        const depthB = (pb[2] + 1.2) / 2.4
        const wA = 0.008 + 0.017 * depthA
        const wB = 0.008 + 0.017 * depthB

        const dx = pb[0] - pa[0], dy = pb[1] - pa[1]
        const len = Math.sqrt(dx * dx + dy * dy) || 1
        const nx = -dy / len, ny = dx / len

        const points = [
          `${pa[0] + nx * wA},${pa[1] + ny * wA}`,
          `${pb[0] + nx * wB},${pb[1] + ny * wB}`,
          `${pb[0] - nx * wB},${pb[1] - ny * wB}`,
          `${pa[0] - nx * wA},${pa[1] - ny * wA}`,
        ].join(' ')

        e.poly.setAttribute('points', points)
        e.poly.setAttribute('fill-opacity', String(opacity));

        (avgZ > 0 ? frontGroup : backGroup).appendChild(e.poly)
      })

      // Depth-scaled dots
      dots.forEach(d => {
        const verts = d.type === 'up' ? up : down
        const p = verts[d.idx]
        const depth = (p[2] + 1.2) / 2.4
        const r = 0.025 + 0.025 * depth
        const opacity = 0.5 + 0.5 * depth

        d.circle.setAttribute('cx', String(p[0]))
        d.circle.setAttribute('cy', String(p[1]))
        d.circle.setAttribute('r', String(r))
        d.circle.setAttribute('fill-opacity', String(opacity));

        (p[2] > 0 ? frontGroup : backGroup).appendChild(d.circle)
      })

      const pulse = reducedMotion ? 0.87 : 0.87 + 0.06 * Math.sin(a * 2)
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
      viewBox="-1.3 -1.3 2.6 2.6"
      className="merkaba-glyph"
    />
  )
}
