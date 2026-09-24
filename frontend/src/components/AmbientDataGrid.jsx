import { useEffect, useRef } from 'react'

const SPACING = 56 // px between grid lines
// Light theme: a near-invisible border-tinted grid (E2E5EA on F6F7F9).
const GRID_ALPHA = 0.35

export default function AmbientDataGrid() {
  const canvasRef = useRef(null)

  // Static backdrop: draw the Cartesian grid once on mount. No animation
  // loop, no repaints; the only redraw is event-driven on window resize.
  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    function draw() {
      const width = window.innerWidth
      const height = window.innerHeight
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      ctx.lineWidth = 1
      ctx.strokeStyle = '#e2e5ea'
      ctx.globalAlpha = GRID_ALPHA
      ctx.beginPath()
      for (let x = 0; x <= width; x += SPACING) {
        ctx.moveTo(x, 0)
        ctx.lineTo(x, height)
      }
      for (let y = 0; y <= height; y += SPACING) {
        ctx.moveTo(0, y)
        ctx.lineTo(width, y)
      }
      ctx.stroke()
      ctx.globalAlpha = 1
    }

    draw()
    window.addEventListener('resize', draw)
    return () => window.removeEventListener('resize', draw)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-[-1]"
    />
  )
}