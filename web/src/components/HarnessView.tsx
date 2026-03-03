import { useCallback, useEffect, useRef, useState } from 'react'
import MerkabaGlyph from './MerkabaGlyph'
import DetailPanel from './DetailPanel'
import type { AgentState, ToolInfo } from '../hooks/useControlSocket'
import { getModels } from '../api/client'

interface Props {
  agent: AgentState
  onBack: () => void
  onModelChange: (model: string) => void
}

// Fallback model list used when /api/system/models is unavailable
const FALLBACK_MODELS = ['qwen3.5:122b', 'qwen3:8b', 'qwen3:4b']

export default function HarnessView({ agent, onBack, onModelChange }: Props) {
  const [selectedTool, setSelectedTool] = useState<ToolInfo | null>(null)
  const [focusedIndex, setFocusedIndex] = useState(-1)
  const toolRefs = useRef<(SVGGElement | null)[]>([])
  const [availableModels, setAvailableModels] = useState<string[]>(FALLBACK_MODELS)

  const cx = 300
  const cy = 250
  const radius = 160
  const tools = agent.tools

  // Load available models from the API on mount; fall back to hardcoded list on error
  useEffect(() => {
    getModels()
      .then(data => {
        const names = data.models.map(m => m.name)
        if (names.length > 0) setAvailableModels(names)
      })
      .catch(() => {
        // API unavailable — keep the hardcoded fallback list already in state
      })
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onBack()
      return
    }
    if (e.key === 'm' || e.key === 'M') {
      // Focus model selector handled by parent
      return
    }

    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = (focusedIndex + 1) % tools.length
      setFocusedIndex(next)
      toolRefs.current[next]?.focus()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prev = (focusedIndex - 1 + tools.length) % tools.length
      setFocusedIndex(prev)
      toolRefs.current[prev]?.focus()
    } else if (e.key === 'Enter' && focusedIndex >= 0) {
      setSelectedTool(tools[focusedIndex])
    }
  }, [focusedIndex, tools, onBack])

  return (
    <div className="harness-view" onKeyDown={handleKeyDown}>
      <div className="harness-main">
        <button className="btn btn-dim harness-back" onClick={onBack}>
          ← Back
        </button>

        <svg className="harness-svg" viewBox="0 0 600 500">
          {/* Connection lines from center to each tool */}
          {tools.map((_, i) => {
            const angle = (2 * Math.PI * i) / tools.length - Math.PI / 2
            const tx = cx + radius * Math.cos(angle)
            const ty = cy + radius * Math.sin(angle)
            return (
              <line
                key={`line-${i}`}
                x1={cx} y1={cy} x2={tx} y2={ty}
                stroke="#3a3a5c"
                strokeWidth="1"
                strokeDasharray="4 3"
                className="harness-line"
              />
            )
          })}

          {/* Center agent */}
          <foreignObject x={cx - 50} y={cy - 50} width={100} height={100} style={{ pointerEvents: 'none' }}>
            <MerkabaGlyph size={100} status="active" speed={1} />
          </foreignObject>

          {/* Agent name */}
          <text x={cx} y={cy + 65} textAnchor="middle" fill="#e0e0ff" fontSize="14" fontFamily="monospace">
            {agent.name}
          </text>

          {/* Tool nodes in orbit */}
          {tools.map((tool, i) => {
            const angle = (2 * Math.PI * i) / tools.length - Math.PI / 2
            const tx = cx + radius * Math.cos(angle)
            const ty = cy + radius * Math.sin(angle)
            const isSelected = selectedTool?.name === tool.name
            const isFocused = focusedIndex === i

            return (
              <g
                key={tool.name}
                ref={el => { toolRefs.current[i] = el }}
                transform={`translate(${tx}, ${ty})`}
                className={`tool-node ${isSelected ? 'tool-node--selected' : ''} ${isFocused ? 'tool-node--focused' : ''}`}
                tabIndex={0}
                role="button"
                aria-label={`${tool.name} — ${tool.tier}`}
                onFocus={() => setFocusedIndex(i)}
                onClick={() => setSelectedTool(tool)}
                onKeyDown={(e) => { if (e.key === 'Enter') setSelectedTool(tool) }}
              >
                <circle
                  r="24"
                  fill="#12121a"
                  stroke={isSelected ? '#00f0ff' : tool.active ? '#6c63ff' : '#3a3a5c'}
                  strokeWidth="1.5"
                />
                <text
                  y="4"
                  textAnchor="middle"
                  fill={tool.active ? '#e0e0ff' : '#5a5a7c'}
                  fontSize="8"
                  fontFamily="monospace"
                >
                  {tool.name.length > 10 ? tool.name.slice(0, 9) + '…' : tool.name}
                </text>
                <text y="36" textAnchor="middle" fill="#8888a0" fontSize="8" fontFamily="monospace">
                  {tool.tier}
                </text>
              </g>
            )
          })}
        </svg>

        {/* Model selector — populated from /api/system/models, falls back to hardcoded list */}
        <div className="harness-model-selector">
          <label className="hud-label" htmlFor="model-select">MODEL</label>
          <select
            id="model-select"
            className="harness-select"
            value={agent.model}
            onChange={(e) => onModelChange(e.target.value)}
          >
            {/* Always include the current agent model even if not in the fetched list */}
            {!availableModels.includes(agent.model) && (
              <option value={agent.model}>{agent.model}</option>
            )}
            {availableModels.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
      </div>

      <DetailPanel tool={selectedTool} />
    </div>
  )
}
