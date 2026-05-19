import React, { useEffect, useImperativeHandle, useRef, useState, forwardRef } from 'react'
import WaveSurfer from 'wavesurfer.js'

const TelnyxDualWaveform = forwardRef(function TelnyxDualWaveform(
  { src, authToken, onPlayingChange, onError, splitChannels = true },
  ref,
) {
  const containerRef = useRef(null)
  const wsRef = useRef(null)
  const objectUrlRef = useRef('')
  const [ready, setReady] = useState(false)
  const [loading, setLoading] = useState(false)
  const [playing, setPlaying] = useState(false)

  const setPlayingState = (value) => {
    setPlaying(value)
    onPlayingChange?.(value)
  }

  useImperativeHandle(ref, () => ({
    play: async () => {
      const ws = wsRef.current
      if (!ws) return
      await ws.play()
    },
    pause: () => {
      wsRef.current?.pause()
    },
    stop: () => {
      const ws = wsRef.current
      if (!ws) return
      ws.pause()
      ws.setTime(0)
      setPlayingState(false)
    },
    isReady: () => ready,
  }))

  useEffect(() => {
    if (!containerRef.current || !src) return undefined
    let cancelled = false
    setLoading(true)
    setReady(false)
    setPlayingState(false)

    const run = async () => {
      try {
        const res = await fetch(src, {
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        })
        if (!res.ok) {
          let detail = ''
          try {
            const body = await res.json()
            detail = body?.detail || body?.message || ''
          } catch {
            try {
              detail = (await res.text()).slice(0, 200)
            } catch {
              detail = ''
            }
          }
          throw new Error(detail || `Could not load recording (${res.status})`)
        }
        const blob = await res.blob()
        if (cancelled) return
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
        const objectUrl = URL.createObjectURL(blob)
        objectUrlRef.current = objectUrl

        const options = {
          container: containerRef.current,
          url: objectUrl,
          height: splitChannels ? 64 : 56,
          normalize: true,
          barWidth: 2,
          barGap: 1,
          waveColor: '#94a3b8',
          progressColor: '#2563eb',
        }
        if (splitChannels) {
          options.splitChannels = [
            { waveColor: '#22c55e', progressColor: '#16a34a' },
            { waveColor: '#3b82f6', progressColor: '#2563eb' },
          ]
        }

        const ws = WaveSurfer.create(options)
        wsRef.current = ws
        ws.on('ready', () => {
          if (!cancelled) {
            setReady(true)
            setLoading(false)
          }
        })
        ws.on('play', () => setPlayingState(true))
        ws.on('pause', () => setPlayingState(false))
        ws.on('finish', () => setPlayingState(false))
      } catch (e) {
        if (!cancelled) {
          setLoading(false)
          onError?.(e?.message || 'Waveform failed')
        }
      }
    }

    void run()
    return () => {
      cancelled = true
      wsRef.current?.destroy()
      wsRef.current = null
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current)
        objectUrlRef.current = ''
      }
    }
  }, [src, authToken, onError, splitChannels])

  const togglePlay = async () => {
    const ws = wsRef.current
    if (!ws || !ready) return
    if (playing) {
      ws.pause()
    } else {
      await ws.play()
    }
  }

  const stopPlayback = () => {
    const ws = wsRef.current
    if (!ws) return
    ws.pause()
    ws.setTime(0)
    setPlayingState(false)
  }

  return (
    <div className='telnyxDualWaveform'>
      {splitChannels ? (
        <div className='telnyxDualWaveformLabels'>
          <span className='telnyxDualWaveformLabel telnyxDualWaveformLabelUser'>Caller</span>
          <span className='telnyxDualWaveformLabel telnyxDualWaveformLabelAgent'>Agent</span>
        </div>
      ) : null}
      <div ref={containerRef} className='telnyxDualWaveformCanvas' />
      <div className='telnyxDualWaveformToolbar'>
        <button type='button' className='btn soft telnyxWaveBtn' onClick={togglePlay} disabled={!ready || loading}>
          {playing ? 'Pause' : 'Play'}
        </button>
        <button type='button' className='btn soft telnyxWaveBtn' onClick={stopPlayback} disabled={!ready || loading}>
          Stop
        </button>
        {loading ? <span className='muted telnyxWaveStatus'>Loading…</span> : null}
        {ready && !loading ? (
          <span className='muted telnyxWaveStatus'>
            {splitChannels
              ? 'Two tracks: caller (green) · agent (blue). Click waveform to seek.'
              : 'Click waveform to seek.'}
          </span>
        ) : null}
      </div>
    </div>
  )
})

export default TelnyxDualWaveform
