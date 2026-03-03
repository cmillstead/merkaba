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

// Shared SVG element cache — created once per component instance via useRef,
// then only setAttribute is called each frame (no DOM creation in the render loop).
interface GlyphElements {
  backGroup: SVGGElement
  orbGroup: SVGGElement
  frontGroup: SVGGElement
  orbCircle: SVGCircleElement
  edges: Array<{ line: SVGLineElement; type: 'up' | 'down'; ia: number; ib: number }>
  dots: Array<{ circle: SVGCircleElement; type: 'up' | 'down'; idx: number }>
}

export default function MerkabaGlyph({ size = 120, status = 'active', speed = 1 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const angleRef = useRef(0)
  const rafRef = useRef<number | undefined>(undefined)
  // Cache DOM elements across renders — rebuilt only when size changes (strokeWidth changes)
  const elementsRef = useRef<GlyphElements | null>(null)
  // Track previous size so we know when to rebuild the cache
  const prevSizeRef = useRef<number | undefined>(undefined)

  // Build (or rebuild) the static SVG structure — called once on mount and when size changes.
  // Status/color changes are handled separately via updateColors() to avoid DOM teardown.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    const ns = 'http://www.w3.org/2000/svg'
    const colors = STATUS_COLORS[status]
    const id = svg.id || `mg-${Math.random().toString(36).slice(2, 8)}`
    svg.id = id

    // Only rebuild DOM structure when size changes (affects strokeWidth/dotRadius).
    // On status-only changes we skip the teardown and just recolor below.
    const sizeChanged = prevSizeRef.current !== size
    if (sizeChanged || !elementsRef.current) {
      // Clear previous content
      while (svg.firstChild) svg.removeChild(svg.firstChild)

      // Gradient defs
      const defs = document.createElementNS(ns, 'defs')
      const orbGrad = document.createElementNS(ns, 'radialGradient')
      orbGrad.id = `${id}-orb`
      const stops: [string, string][] = [
        ['0%',   'rgba(210,200,255,1)'],
        ['10%',  'rgba(150,130,240,0.9)'],
        ['22%',  'rgba(90,70,200,0.6)'],
        ['38%',  'rgba(50,38,140,0.3)'],
        ['58%',  'rgba(30,22,90,0.1)'],
        ['100%', 'rgba(20,16,60,0.0)'],
      ]
      stops.forEach(([off, col]) => {
        const st = document.createElementNS(ns, 'stop')
        st.setAttribute('offset', off)
        st.setAttribute('stop-color', col)
        orbGrad.appendChild(st)
      })
      defs.appendChild(orbGrad)
      svg.appendChild(defs)

      // Z-sorted layer groups: back lines → orb → front lines
      const backGroup = document.createElementNS(ns, 'g')
      const orbGroup = document.createElementNS(ns, 'g')
      const frontGroup = document.createElementNS(ns, 'g')
      svg.appendChild(backGroup)
      svg.appendChild(orbGroup)
      svg.appendChild(frontGroup)

      // Orb circle — created once, r updated each frame for pulse
      const orbCircle = document.createElementNS(ns, 'circle')
      orbCircle.setAttribute('cx', '0')
      orbCircle.setAttribute('cy', '0')
      orbCircle.setAttribute('r', '0.9')
      orbCircle.setAttribute('fill', `url(#${id}-orb)`)
      orbGroup.appendChild(orbCircle)

      const strokeWidth = size < 100 ? '0.045' : '0.025'
      const dotRadius = size < 100 ? '0.06' : '0.04'

      // Create edge line elements once — positions updated via setAttribute each frame
      const edges: GlyphElements['edges'] = []
      EDGES.forEach(([ia, ib]) => {
        const l = document.createElementNS(ns, 'line')
        l.setAttribute('stroke', colors.up)
        l.setAttribute('stroke-width', strokeWidth)
        edges.push({ line: l, type: 'up', ia, ib })
      })
      EDGES.forEach(([ia, ib]) => {
        const l = document.createElementNS(ns, 'line')
        l.setAttribute('stroke', colors.down)
        l.setAttribute('stroke-width', strokeWidth)
        edges.push({ line: l, type: 'down', ia, ib })
      })

      // Create dot circle elements once — cx/cy updated each frame
      const dots: GlyphElements['dots'] = []
      UP_VERTS.forEach((_, i) => {
        const c = document.createElementNS(ns, 'circle')
        c.setAttribute('r', dotRadius)
        c.setAttribute('fill', colors.up)
        dots.push({ circle: c, type: 'up', idx: i })
      })
      DOWN_VERTS.forEach((_, i) => {
        const c = document.createElementNS(ns, 'circle')
        c.setAttribute('r', dotRadius)
        c.setAttribute('fill', colors.down)
        dots.push({ circle: c, type: 'down', idx: i })
      })

      elementsRef.current = { backGroup, orbGroup, frontGroup, orbCircle, edges, dots }
      prevSizeRef.current = size
    } else {
      // Size unchanged — only update colors on the already-created elements
      const { edges, dots } = elementsRef.current
      edges.forEach(e => {
        e.line.setAttribute('stroke', e.type === 'up' ? colors.up : colors.down)
      })
      dots.forEach(d => {
        d.circle.setAttribute('fill', d.type === 'up' ? colors.up : colors.down)
      })
    }
  }, [size, status])

  // Animation loop — depends only on speed; runs independently of status/size re-renders.
  // Uses elementsRef to access DOM nodes without recreating them.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    const tiltX = 0.35
    const baseSpeed = 0.008

    function render() {
      const els = elementsRef.current
      if (!els) {
        rafRef.current = requestAnimationFrame(render)
        return
      }

      angleRef.current += baseSpeed * speed
      const a = angleRef.current

      function xform(verts: [number, number, number][]) {
        return verts.map(v => rotateX(rotateY(v, a), tiltX))
      }

      const up = xform(UP_VERTS)
      const down = xform(DOWN_VERTS)
      const { backGroup, frontGroup, orbCircle, edges, dots } = els

      // Clear z-sorted groups each frame — only group membership changes,
      // the elements themselves are reused (no createElement in hot path)
      while (backGroup.firstChild) backGroup.removeChild(backGroup.firstChild)
      while (frontGroup.firstChild) frontGroup.removeChild(frontGroup.firstChild)

      // Update edge positions and sort into front/back groups by z-depth
      edges.forEach(e => {
        const verts = e.type === 'up' ? up : down
        const avgZ = (verts[e.ia][2] + verts[e.ib][2]) / 2
        const opacity = 0.4 + 0.5 * (avgZ + 1.2) / 2.4

        e.line.setAttribute('x1', String(verts[e.ia][0]))
        e.line.setAttribute('y1', String(verts[e.ia][1]))
        e.line.setAttribute('x2', String(verts[e.ib][0]))
        e.line.setAttribute('y2', String(verts[e.ib][1]))
        e.line.setAttribute('stroke-opacity', String(opacity));

        (avgZ > 0 ? frontGroup : backGroup).appendChild(e.line)
      })

      // Update dot positions and sort by z-depth
      dots.forEach(d => {
        const verts = d.type === 'up' ? up : down
        const p = verts[d.idx]
        d.circle.setAttribute('cx', String(p[0]))
        d.circle.setAttribute('cy', String(p[1]));
        (p[2] > 0 ? frontGroup : backGroup).appendChild(d.circle)
      })

      // Subtle pulse on orb radius
      const pulse = 0.87 + 0.06 * Math.sin(a * 2)
      orbCircle.setAttribute('r', String(pulse))

      rafRef.current = requestAnimationFrame(render)
    }

    // Cancel any existing RAF before starting a new loop (speed changed)
    if (rafRef.current !== undefined) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(render)

    return () => {
      if (rafRef.current !== undefined) cancelAnimationFrame(rafRef.current)
    }
  }, [speed])

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
