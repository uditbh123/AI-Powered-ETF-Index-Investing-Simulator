import { useEffect, useRef } from 'react'

const SPACING = 56 // px between grid lines
const DRIFT_X = 0.014 // px per ms (slow, constant horizontal drift)
const DRIFT_Y = 0.01 // px per ms (slow, constant vertical drift)
const MAX_NODES = 5 // concurrent data nodes
const NODE_SPAWN_P = 0.004 // spawn chance per frame (~0.24/s at 60fps)

function mod(value, divisor) {
  return ((value % divisor) + divisor) % divisor
}

export default function AmbientDataGrid() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    let width = 0
    let height = 0
    let rafId = 0
    let offX = 0
    let offY = 0
    let last = performance.now()
    const nodes = []

    function resize() {
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
    }

    // Screen position of a drifting grid line, given its index.
    const rowY = (index) => index * SPACING + offY
    const colX = (index) => index * SPACING + offX

    function spawnNode() {
      if (Math.random() < 0.5) {
        // Row node: traverses a horizontal grid line left -> right
        const index = Math.floor((height + SPACING) / SPACING)
        nodes.push({
          kind: 'row',
          index: Math.floor(Math.random() * (index + 1)),
          pos: mod(offX, SPACING) - SPACING, // start just off-screen left
          speed: 0.04 + Math.random() * 0.03,
        })
      } else {
        // Column node: traverses a vertical grid line top -> bottom
        const index = Math.floor((width + SPACING) / SPACING)
        nodes.push({
          kind: 'col',
          index: Math.floor(Math.random() * (index + 1)),
          pos: mod(offY, SPACING) - SPACING, // start just off-screen top
          speed: 0.04 + Math.random() * 0.03,
        })
      }
    }

    function tick(now) {
      const dt = Math.min(now - last, 50)
      last = now
      offX += DRIFT_X * dt
      offY += DRIFT_Y * dt

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)

      // Drifting Cartesian grid: pure white, extremely low opacity
      ctx.lineWidth = 1
      ctx.strokeStyle = '#ffffff'
      ctx.globalAlpha = 0.03
      ctx.beginPath()
      const firstCol = mod(offX, SPACING)
      for (let x = firstCol - SPACING; x <= width + SPACING; x += SPACING) {
        ctx.moveTo(x, 0)
        ctx.lineTo(x, height)
      }
      const firstRow = mod(offY, SPACING)
      for (let y = firstRow - SPACING; y <= height + SPACING; y += SPACING) {
        ctx.moveTo(0, y)
        ctx.lineTo(width, y)
      }
      ctx.stroke()

      // Occasionally fire a brighter data node onto a random grid line
      if (nodes.length < MAX_NODES && Math.random() < NODE_SPAWN_P) spawnNode()

      // Advance + draw active nodes (opacity 0.1)
      ctx.fillStyle = '#ffffff'
      ctx.globalAlpha = 0.1
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        const node = nodes[i]
        node.pos += node.speed * dt
        if (node.kind === 'row') {
          const y = rowY(node.index)
          const x = node.pos
          if (x > width + SPACING) {
            nodes.splice(i, 1)
            continue
          }
          ctx.fillRect(x, y - 0.75, 2.5, 1.5)
        } else {
          const x = colX(node.index)
          const y = node.pos
          if (y > height + SPACING) {
            nodes.splice(i, 1)
            continue
          }
          ctx.fillRect(x - 0.75, y, 1.5, 2.5)
        }
      }

      ctx.globalAlpha = 1
      rafId = requestAnimationFrame(tick)
    }

    resize()
    window.addEventListener('resize', resize)
    rafId = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-[-1] h-full w-full"
    />
  )
}