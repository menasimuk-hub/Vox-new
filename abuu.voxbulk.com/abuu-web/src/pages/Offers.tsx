import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

function shekel(agorot) {
  return `${(Number(agorot || 0) / 100).toFixed(2)} ₪`
}

const emptyOffer = {
  title_en: '',
  title_ar: '',
  offer_price_agorot: 0,
  original_price_agorot: 0,
  tags: ['chicken'],
  is_active: true,
}

export default function Offers() {
  const [offers, setOffers] = useState([])
  const [menu, setMenu] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [draft, setDraft] = useState(emptyOffer)
  const [selectedItems, setSelectedItems] = useState([])

  const menuItems = useMemo(() => {
    const rows = []
    for (const cat of menu) {
      for (const item of cat.items || []) rows.push(item)
    }
    return rows
  }, [menu])

  const load = useCallback(async () => {
    const [offerRows, menuRows] = await Promise.all([
      apiFetch('/abuu/restaurant/offers'),
      apiFetch('/abuu/restaurant/menu'),
    ])
    setOffers(Array.isArray(offerRows) ? offerRows : [])
    setMenu(Array.isArray(menuRows) ? menuRows : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const createOffer = async () => {
    setBusy('create')
    try {
      await apiFetch('/abuu/restaurant/offers', {
        method: 'POST',
        body: JSON.stringify({
          ...draft,
          offer_price_agorot: Math.round(Number(draft.offer_price_agorot || 0)),
          original_price_agorot: Math.round(Number(draft.original_price_agorot || 0)),
          items: selectedItems.map((itemId) => ({ menu_item_id: itemId, quantity: 1 })),
          tags: draft.tags,
        }),
      })
      setDraft(emptyOffer)
      setSelectedItems([])
      await load()
    } catch (e) {
      setError(e.message || 'Create offer failed')
    } finally {
      setBusy('')
    }
  }

  const toggleOffer = async (offer) => {
    setBusy(offer.id)
    try {
      await apiFetch(`/abuu/restaurant/offers/${offer.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !offer.is_active }),
      })
      await load()
    } catch (e) {
      setError(e.message || 'Update failed')
    } finally {
      setBusy('')
    }
  }

  const deleteOffer = async (offerId) => {
    setBusy(offerId)
    try {
      await apiFetch(`/abuu/restaurant/offers/${offerId}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      setError(e.message || 'Delete failed')
    } finally {
      setBusy('')
    }
  }

  if (loading) return <p>Loading offers…</p>

  return (
    <div className='stack'>
      <h1>Promo Offers</h1>
      {error ? <p className='error'>{error}</p> : null}

      <section className='card stack'>
        <h2>Add offer</h2>
        <div className='grid2'>
          <label>
            Title (English)
            <input value={draft.title_en} onChange={(e) => setDraft({ ...draft, title_en: e.target.value })} />
          </label>
          <label>
            Title (Arabic)
            <input value={draft.title_ar} onChange={(e) => setDraft({ ...draft, title_ar: e.target.value })} />
          </label>
          <label>
            Offer price (agorot)
            <input
              type='number'
              value={draft.offer_price_agorot}
              onChange={(e) => setDraft({ ...draft, offer_price_agorot: e.target.value })}
            />
          </label>
          <label>
            Original price (agorot)
            <input
              type='number'
              value={draft.original_price_agorot}
              onChange={(e) => setDraft({ ...draft, original_price_agorot: e.target.value })}
            />
          </label>
          <label>
            Tag
            <select
              value={draft.tags[0] || 'chicken'}
              onChange={(e) => setDraft({ ...draft, tags: [e.target.value] })}
            >
              <option value='chicken'>Chicken</option>
              <option value='fish'>Fish</option>
              <option value='meat'>Meat</option>
            </select>
          </label>
        </div>
        <label>
          Menu items in offer
          <select
            multiple
            value={selectedItems}
            onChange={(e) => setSelectedItems(Array.from(e.target.selectedOptions, (o) => o.value))}
            style={{ minHeight: 120 }}
          >
            {menuItems.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name_en} — {shekel(item.price_agorot)}
              </option>
            ))}
          </select>
        </label>
        <button type='button' className='btn primary' disabled={busy === 'create'} onClick={createOffer}>
          Create offer
        </button>
      </section>

      <section className='card stack'>
        <h2>Active offers</h2>
        {!offers.length ? <p>No offers yet.</p> : null}
        {offers.map((offer) => (
          <article key={offer.id} className='row between'>
            <div>
              <strong>{offer.title_en}</strong>
              <div>{offer.title_ar}</div>
              <div>
                {shekel(offer.offer_price_agorot)}
                {offer.original_price_agorot > offer.offer_price_agorot ? (
                  <span className='muted'> (was {shekel(offer.original_price_agorot)})</span>
                ) : null}
              </div>
              <div className='muted'>{(offer.tags || []).join(', ')}</div>
            </div>
            <div className='row gap'>
              <button type='button' className='btn' disabled={busy === offer.id} onClick={() => toggleOffer(offer)}>
                {offer.is_active ? 'Disable' : 'Enable'}
              </button>
              <button type='button' className='btn danger' disabled={busy === offer.id} onClick={() => deleteOffer(offer.id)}>
                Delete
              </button>
            </div>
          </article>
        ))}
      </section>
    </div>
  )
}
