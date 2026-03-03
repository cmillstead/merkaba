import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import MerkabaGlyph from './MerkabaGlyph.tsx'
import type { AgentState, WorkerState, Connection } from '../hooks/useControlSocket.ts'

interface Props {
  agents: AgentState[]
  workers: WorkerState[]
  connections: Connection[]
  onSelectNode: (nodeId: string, nodeType: 'agent' | 'worker') => void
}

interface NodePosition {
  id: string
  x: number
  y: number
  type: 'agent' | 'worker'
}

function computeLayout(agents: AgentState[], workers: WorkerState[]): NodePosition[] {
  const positions: NodePosition[] = []
  const cx = 400
  const cy = 300

  // Primary agent at center
  if (agents.length > 0) {
    positions.push({ id: agents[0].id, x: cx, y: cy, type: 'agent' })
  }

  // Workers in a circle around the agent
  const radius = 200
  workers.forEach((w, i) => {
    const angle = (2 * Math.PI * i) / workers.length - Math.PI / 2
    positions.push({
      id: w.id,
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
      type: 'worker',
    })
  })

  return positions
}

export default function ConstellationMap({ agents, workers, connections, onSelectNode }: Props) {
  const positions = useMemo(() => computeLayout(agents, workers), [agents, workers])
  const [focusedIndex, setFocusedIndex] = useState(0)
  const nodesRef = useRef<(SVGGElement | null)[]>([])

  const statusFor = useCallback((id: string): 'active' | 'idle' | 'scheduled' | 'error' => {
    const agent = agents.find(a => a.id === id)
    if (agent) return agent.status === 'active' ? 'active' : 'idle'
    const worker = workers.find(w => w.id === id)
    if (!worker) return 'idle'
    if (worker.status === 'active') return 'active'
    if (worker.scheduled) return 'scheduled'
    return 'idle'
  }, [agents, workers])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const current = positions[focusedIndex]
    if (!current) return

    if (e.key === 'Enter') {
      const pos = positions[focusedIndex]
      onSelectNode(pos.id, pos.type)
      return
    }

    if (e.key === 'Tab') return // Let default tab behavior work

    // Arrow key spatial navigation
    let dx = 0, dy = 0
    if (e.key === 'ArrowUp') dy = -1
    else if (e.key === 'ArrowDown') dy = 1
    else if (e.key === 'ArrowLeft') dx = -1
    else if (e.key === 'ArrowRight') dx = 1
    else return

    e.preventDefault()

    // Find nearest node in the arrow direction
    let bestIndex = focusedIndex
    let bestDist = Infinity

    positions.forEach((pos, i) => {
      if (i === focusedIndex) return
      const ddx = pos.x - current.x
      const ddy = pos.y - current.y
      // Only consider nodes in the pressed direction
      if (dx !== 0 && Math.sign(ddx) !== dx) return
      if (dy !== 0 && Math.sign(ddy) !== dy) return
      const dist = Math.sqrt(ddx * ddx + ddy * ddy)
      if (dist < bestDist) {
        bestDist = dist
        bestIndex = i
      }
    })

    if (bestIndex !== focusedIndex) {
      setFocusedIndex(bestIndex)
      nodesRef.current[bestIndex]?.focus()
    }
  }, [focusedIndex, positions, onSelectNode])

  // Focus first node on mount
  useEffect(() => {
    nodesRef.current[0]?.focus()
  }, [])

  const getPos = (id: string) => positions.find(p => p.id === id)

  return (
    <svg
      className="constellation-map"
      viewBox="0 0 800 600"
      onKeyDown={handleKeyDown}
    >
      {/* Background grid */}
      <defs>
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1a1a3e" strokeWidth="0.5" />
        </pattern>
        <radialGradient id="orb-fill">
          <stop offset="0%" stopColor="#b0a0ff" />
          <stop offset="6%" stopColor="#7868d8" />
          <stop offset="18%" stopColor="#3a2e80" />
          <stop offset="35%" stopColor="#161638" />
          <stop offset="100%" stopColor="#12121a" />
        </radialGradient>
        <radialGradient id="orb-outer-glow">
          <stop offset="78%" stopColor="rgba(80, 70, 200, 0.2)" />
          <stop offset="92%" stopColor="rgba(0, 180, 255, 0.08)" />
          <stop offset="100%" stopColor="transparent" />
        </radialGradient>
        <radialGradient id="orb-vignette">
          <stop offset="0%" stopColor="transparent" />
          <stop offset="50%" stopColor="transparent" />
          <stop offset="75%" stopColor="rgba(8, 8, 20, 0.35)" />
          <stop offset="90%" stopColor="rgba(8, 8, 20, 0.65)" />
          <stop offset="100%" stopColor="rgba(8, 8, 20, 0.9)" />
        </radialGradient>
      </defs>
      <rect width="800" height="600" fill="url(#grid)" />

      {/* Connection lines */}
      {connections.map((conn, i) => {
        const from = getPos(conn.from)
        const to = getPos(conn.to)
        if (!from || !to) return null
        return (
          <line
            key={i}
            x1={from.x} y1={from.y}
            x2={to.x} y2={to.y}
            className="constellation-line"
            stroke="#3a3a5c"
            strokeWidth="1"
            strokeDasharray="6 4"
          />
        )
      })}

      {/* Nodes */}
      {positions.map((pos, i) => {
        const isAgent = pos.type === 'agent'
        const status = statusFor(pos.id)
        const label = isAgent
          ? agents.find(a => a.id === pos.id)?.name ?? pos.id
          : workers.find(w => w.id === pos.id)?.name ?? pos.id

        return (
          <g
            key={pos.id}
            ref={el => { nodesRef.current[i] = el }}
            transform={`translate(${pos.x}, ${pos.y})`}
            className={`constellation-node constellation-node--${status}`}
            tabIndex={0}
            role="button"
            aria-label={`${label} — ${status}`}
            onFocus={() => setFocusedIndex(i)}
            onClick={() => onSelectNode(pos.id, pos.type)}
            onKeyDown={(e) => { if (e.key === 'Enter') onSelectNode(pos.id, pos.type) }}
          >
            {/* Outer glow (agent only) */}
            {isAgent && (
              <circle r={56} fill="url(#orb-outer-glow)" />
            )}
            {/* Glow circle behind node */}
            <circle
              r={isAgent ? 50 : 35}
              fill="transparent"
              className="constellation-glow"
            />
            {/* Node circle — agent uses orb gradient, workers stay flat */}
            <circle
              r={isAgent ? 40 : 28}
              fill={isAgent ? 'url(#orb-fill)' : '#12121a'}
              stroke={status === 'active' ? '#00f0ff' : '#3a3a5c'}
              strokeWidth="1.5"
            />
            {/* Label */}
            <text
              y={isAgent ? 55 : 42}
              textAnchor="middle"
              fill="#e0e0ff"
              fontSize={isAgent ? 13 : 11}
              fontFamily="monospace"
            >
              {label}
            </text>
            {/* Status indicator */}
            <circle
              cx={isAgent ? 30 : 20}
              cy={isAgent ? -30 : -20}
              r="4"
              fill={status === 'active' ? '#00f0ff' : status === 'scheduled' ? '#fbbf24' : status === 'error' ? '#ff6b35' : '#3a3a5c'}
            />
          </g>
        )
      })}

      {/* Merkaba glyph rendered via foreignObject for the primary agent */}
      {positions.length > 0 && positions[0].type === 'agent' && (
        <>
          {/* Clip wireframe to sphere boundary so vertices disappear behind the orb edge */}
          <clipPath id="orb-clip">
            <circle cx={positions[0].x} cy={positions[0].y} r={38} />
          </clipPath>
          <g clipPath="url(#orb-clip)" style={{ pointerEvents: 'none' }}>
            <foreignObject
              x={positions[0].x - 35}
              y={positions[0].y - 35}
              width={70}
              height={70}
              style={{ overflow: 'visible' }}
            >
              <MerkabaGlyph size={70} status={statusFor(positions[0].id)} speed={1} />
            </foreignObject>
          </g>
          {/* Vignette on top — darkens wireframe at sphere edges */}
          <circle
            cx={positions[0].x}
            cy={positions[0].y}
            r={40}
            fill="url(#orb-vignette)"
            style={{ pointerEvents: 'none' }}
          />
        </>
      )}
    </svg>
  )
}
