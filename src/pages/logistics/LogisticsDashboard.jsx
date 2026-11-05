import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Clock3, MapPinned, PackageCheck, RefreshCw, Route, Store, Truck, Pause, Play, RotateCcw, Crosshair, Maximize2 } from 'lucide-react'
import RouteMap from '../../components/logistics/RouteMap'
import RouteComparisonCard from '../../components/logistics/RouteComparisonCard'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import { getStopOrders, logisticsCounts, logisticsStops, routeComparison, totalRouteQuantityKg } from '../../data/logistics'
import { useApp } from '../../context/useApp'
import { shipmentService } from '../../services/api'

const STATUS = { calculating: ['Calculating route…', 'bg-amber-100 text-amber-500'], ready: ['Live route ready', 'bg-leaf-100 text-forest-700'], 'directions-error': ['Demo route ready', 'bg-amber-100 text-amber-700'], unavailable: ['Map unavailable', 'bg-ink-100 text-ink-700'] }

export default function LogisticsDashboard() {
  const [selectedStopId, setSelectedStopId] = useState('kolar')
  const [shipments, setShipments] = useState([])
  const [selectedShipmentId, setSelectedShipmentId] = useState('')
  const [routeState, setRouteState] = useState({ status: 'calculating' })
  const [refreshToken, setRefreshToken] = useState(0)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [tracking, setTracking] = useState(false)
  const [liveLocation, setLiveLocation] = useState(null)
  const [gpsShipmentId, setGpsShipmentId] = useState(null)
  const [gpsError, setGpsError] = useState('')
  const gpsWatchRef = useRef(null)
  const lastGpsReportRef = useRef(0)
  const [trackingState, setTrackingState] = useState({ progress: 0, currentStopId: 'kolar', remainingKm: Number.parseFloat(routeComparison.optimized.distance) })
  const [viewAction, setViewAction] = useState('')
  const onRouteState = useCallback((next) => setRouteState(next), [])
  const onSelectStop = useCallback((id) => setSelectedStopId(id), [])
  const onTrackingUpdate = useCallback((next) => { setTrackingState(next); setSelectedStopId(next.currentStopId) }, [])
  const activeShipment = shipments.find((shipment) => shipment.id === selectedShipmentId) || shipments.find((shipment) => ['In Transit', 'Scheduled', 'Confirmed', 'Disrupted'].includes(shipment.status)) || null
  const savedStops = useMemo(() => (activeShipment?.stops || [])
    .filter((stop) => stop?.position && Number.isFinite(stop.position.lat) && Number.isFinite(stop.position.lng))
    .sort((a, b) => a.sequence - b.sequence), [activeShipment])
  const displayedStops = savedStops.length >= 2 ? savedStops : logisticsStops
  const isSavedRoute = Boolean(activeShipment && savedStops.length >= 2)
  const routeItems = activeShipment?.items || []
  const selectedLiveLocation = liveLocation?.shipmentId === activeShipment?.id ? liveLocation : null
  const shipmentOrderCount = new Set(routeItems.map((item) => item.orderId).filter(Boolean)).size
  const pickupCount = displayedStops.filter((stop) => stop.type === 'pickup').length
  const deliveryCount = displayedStops.filter((stop) => stop.type === 'delivery').length
  const [statusText, statusClass] = STATUS[routeState.status] || STATUS.calculating
  const effectiveSelectedStopId = displayedStops.some((stop) => stop.id === selectedStopId)
    ? selectedStopId
    : displayedStops[0]?.id
  const selectedStop = displayedStops.find((stop) => stop.id === effectiveSelectedStopId)
  const currentStopIndex = displayedStops.findIndex((stop) => stop.id === trackingState.currentStopId)
  const nextStop = displayedStops[Math.min(Math.max(currentStopIndex + 1, 0), displayedStops.length - 1)]
  const summary = routeState.status === 'ready'
    ? [`${routeState.distance} total road distance`, `${routeState.duration} estimated travel time`]
    : routeState.status === 'directions-error'
      ? [`${routeState.distance} simulated route distance`, `${routeState.duration} simulated travel time`]
      : ['Route estimates appear when Google Directions is available', 'Offline stop sequence remains available']

  useEffect(() => {
    let active = true
    shipmentService.list().then((result) => {
      if (!active || result.source !== 'backend') return
      setShipments(result.items)
      const preferred = result.items.find((shipment) => shipment.status === 'In Transit') || result.items.find((shipment) => ['Scheduled', 'Confirmed', 'Disrupted'].includes(shipment.status))
      if (preferred) setSelectedShipmentId(preferred.id)
    }).catch(() => {})
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    if (!activeShipment?.id) {
      return () => { active = false }
    }
    shipmentService.getLocation(activeShipment.id).then((location) => {
      if (active) setLiveLocation(location)
    }).catch(() => {
      if (active) setLiveLocation(null)
    })
    return () => { active = false }
  }, [activeShipment?.id])

  const stopGpsTracking = useCallback(() => {
    if (gpsWatchRef.current !== null) {
      navigator.geolocation?.clearWatch(gpsWatchRef.current)
      gpsWatchRef.current = null
    }
    setGpsShipmentId(null)
  }, [])

  const startGpsTracking = useCallback(() => {
    if (!activeShipment?.id || activeShipment.status !== 'In Transit') return
    if (!navigator.geolocation) {
      setGpsError('This browser does not support device location.')
      return
    }
    stopGpsTracking()
    setGpsError('')
    const shipmentId = activeShipment.id
    gpsWatchRef.current = navigator.geolocation.watchPosition(async (position) => {
      const now = Date.now()
      if (now - lastGpsReportRef.current < 15000) return
      lastGpsReportRef.current = now
      try {
        const saved = await shipmentService.reportLocation(shipmentId, {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracyMeters: position.coords.accuracy,
        })
        setLiveLocation(saved)
      } catch (error) {
        setGpsError(`Location was not saved: ${error.message}`)
      }
    }, (error) => {
      setGpsError(error.message || 'Location permission was denied.')
      stopGpsTracking()
    }, { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 })
    setGpsShipmentId(shipmentId)
  }, [activeShipment, stopGpsTracking])

  useEffect(() => () => stopGpsTracking(), [stopGpsTracking])

  const handleShipmentSaved = useCallback((shipment) => {
    setShipments((current) => [shipment, ...current.filter((item) => item.id !== shipment.id)])
    if (shipment.status !== 'Cancelled') setSelectedShipmentId(shipment.id)
  }, [])

  return <div className="space-y-5">
    <ShipmentOperations onShipmentSaved={handleShipmentSaved} />
    <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="font-display text-xl font-bold text-ink-900">{isSavedRoute ? `Shipment ${activeShipment.id}` : 'Today’s consolidated run'}</h2><p className="text-sm text-ink-500 mt-1">{isSavedRoute ? `${activeShipment.origin} → ${activeShipment.destination} · ${activeShipment.status}` : 'No saved shipment route is available; showing the demonstration route.'}</p></div><span className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${statusClass}`}><i className="h-2 w-2 rounded-full bg-current" />{statusText}</span></div>

    {shipments.length > 0 && <label className="flex max-w-xl items-center gap-3 text-sm text-ink-600">Track saved shipment <select className="min-w-0 flex-1 rounded-lg border border-ink-200 bg-white px-3 py-2 text-ink-900" value={activeShipment?.id || ''} onChange={(event) => setSelectedShipmentId(event.target.value)}>{shipments.filter((shipment) => shipment.stops?.length >= 2).map((shipment) => <option key={shipment.id} value={shipment.id}>{shipment.id} · {shipment.status} · {shipment.vehicleName}</option>)}</select></label>}

    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <Kpi icon={Truck} label="Tracked run" value={activeShipment?.id || 'Demo route'} /><Kpi icon={PackageCheck} label="Orders" value={`${isSavedRoute ? shipmentOrderCount : logisticsCounts.orders}`} /><Kpi icon={MapPinned} label="Stops" value={`${displayedStops.length}`} /><Kpi icon={Store} label="Pickup hubs" value={`${pickupCount}`} /><Kpi icon={Route} label="Delivery stops" value={`${deliveryCount}`} />
    </div>

    <div className="grid lg:grid-cols-[minmax(0,2.1fr)_minmax(300px,0.9fr)] gap-5">
      <section className="card p-3 sm:p-4"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div><h3 className="font-display font-semibold text-sm text-ink-900">Route map</h3><p className="text-xs text-ink-500">{isSavedRoute ? 'Saved shipment stops and current fulfillment state.' : 'Live road routing needs a Google Maps key; the offline route preview remains interactive.'}</p></div><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => setViewAction(`recenter-${Date.now()}`)} disabled={routeState.offline}><Crosshair size={14} /> Recenter</Button><Button size="sm" variant="outline" onClick={() => setViewAction(`fit-${Date.now()}`)} disabled={routeState.offline}><Maximize2 size={14} /> Fit stops</Button><Button size="sm" variant="outline" onClick={() => setRefreshToken((value) => value + 1)}><RefreshCw size={14} /> Recalculate</Button><Button size="sm" onClick={() => setDetailsOpen(true)}>View details</Button></div></div><RouteMap stops={displayedStops} liveLocation={selectedLiveLocation} selectedStopId={effectiveSelectedStopId} onSelectStop={onSelectStop} onRouteState={onRouteState} refreshToken={refreshToken} tracking={tracking} trackingProgress={trackingState.progress} onTrackingUpdate={onTrackingUpdate} viewAction={viewAction} /><div className="mt-3 grid sm:grid-cols-2 gap-2 text-xs">{summary.map((item) => <div key={item} className="flex items-center gap-2 rounded-lg bg-leaf-50 px-3 py-2 text-forest-800"><Clock3 size={13} />{item}</div>)}</div></section>
      <aside className="space-y-4"><div className="card p-4"><h3 className="font-display font-semibold text-sm text-ink-900">Route summary</h3><div className="mt-3 space-y-3"><Metric label="Total distance" value={routeState.distance || 'Calculating…'} /><Metric label="Estimated travel time" value={routeState.duration || 'Calculating…'} /><Metric label="Stops · orders" value={`${displayedStops.length} · ${isSavedRoute ? shipmentOrderCount : logisticsCounts.orders}`} /><Metric label="Total quantity" value={`${isSavedRoute ? Number(activeShipment.currentPayloadKg).toLocaleString('en-IN') : totalRouteQuantityKg.toLocaleString('en-IN')} kg`} /></div></div><div className="card p-4"><div className="flex justify-between"><h3 className="font-display font-semibold text-sm">{activeShipment?.vehicleName || 'FarmLink Truck 01'}</h3><span className={`text-[10px] font-bold ${gpsShipmentId === activeShipment?.id ? 'text-blue-700' : isSavedRoute ? 'text-forest-700' : 'text-clay-500'}`}>● {gpsShipmentId === activeShipment?.id ? 'LIVE GPS' : isSavedRoute ? activeShipment.status.toUpperCase() : 'DEMO LIVE'}</span></div><p className="mt-1 text-xs text-ink-500">{gpsShipmentId === activeShipment?.id ? 'The delivery device is reporting GPS positions to the saved shipment.' : isSavedRoute ? 'Start live GPS from the delivery device to replace the visual route preview.' : 'Simulated vehicle motion — not GPS data.'}</p><p className="mt-3 text-sm font-medium text-ink-900">Current: {selectedLiveLocation ? `${selectedLiveLocation.latitude.toFixed(5)}, ${selectedLiveLocation.longitude.toFixed(5)}` : displayedStops.find((stop) => stop.id === trackingState.currentStopId)?.name || displayedStops[0]?.name}</p>{selectedLiveLocation && <p className="text-xs text-ink-500">GPS accuracy: {Math.round(selectedLiveLocation.accuracyMeters || 0)} m · reported {new Date(selectedLiveLocation.recordedAt).toLocaleTimeString()}</p>}<p className="text-xs text-ink-500">Next: {nextStop?.name} · {trackingState.remainingKm ?? '—'} km remaining</p><p className="text-xs text-ink-500">Progress {trackingState.progress}% · ETA {routeState.duration || 'pending'}</p>{gpsError && <p className="mt-2 text-xs text-clay-600">{gpsError}</p>}<div className="mt-3 h-2 overflow-hidden rounded-full bg-ink-100"><div className="h-full bg-forest-600 transition-all duration-700" style={{ width: `${trackingState.progress}%` }} /></div><div className="mt-3 flex flex-wrap gap-2">{activeShipment?.status === 'In Transit' && <Button size="sm" variant={gpsShipmentId === activeShipment?.id ? 'outline' : 'primary'} onClick={gpsShipmentId === activeShipment?.id ? stopGpsTracking : startGpsTracking}>{gpsShipmentId === activeShipment?.id ? <><Pause size={13} /> Stop GPS</> : <><Play size={13} /> Start live GPS</>}</Button>}<Button size="sm" onClick={() => setTracking((value) => !value)} disabled={!['ready', 'directions-error'].includes(routeState.status)}>{tracking ? <><Pause size={13} /> Pause</> : <><Play size={13} /> Start preview</>}</Button><Button size="sm" variant="outline" onClick={() => { setTracking(false); setTrackingState({ progress: 0, currentStopId: displayedStops[0]?.id || '', remainingKm: Number.parseFloat(routeState.distance) || 0 }); setSelectedStopId(displayedStops[0]?.id || '') }}><RotateCcw size={13} /> Reset</Button></div></div><RouteComparisonCard baseline={isSavedRoute ? { distance: `${activeShipment.plannedDistanceKm} km`, time: `${activeShipment.plannedDurationHours}h`, cost: activeShipment.baselineCost } : routeComparison.baseline} optimized={isSavedRoute ? { distance: `${activeShipment.plannedDistanceKm} km`, time: `${activeShipment.plannedDurationHours}h`, cost: activeShipment.optimizedCost } : routeComparison.optimized} /><StopSelector stops={displayedStops} selectedId={effectiveSelectedStopId} onSelect={onSelectStop} /></aside>
    </div>
    <div className="card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div><h3 className="font-display font-semibold text-sm text-ink-900">Order consolidation</h3><p className="mt-1 text-sm text-ink-700">{isSavedRoute ? `${shipmentOrderCount} saved order(s) and ${routeItems.filter((item) => !item.orderId).length} pooled lot(s) are in the selected shipment.` : `${logisticsCounts.orders} demo orders from ${logisticsCounts.fpos} FPOs are grouped for ${logisticsCounts.buyers} Bengaluru buyers.`}</p></div><Button variant="secondary" onClick={() => setDetailsOpen(true)}>Open Route Details</Button></div>
    {!isSavedRoute && <p className="text-[11px] text-ink-400">Prototype route simulation — fixed stop order and comparison figures are demonstration values.</p>}
    <RouteDetailsDrawer open={detailsOpen} onClose={() => setDetailsOpen(false)} selectedStop={selectedStop} onSelect={onSelectStop} stops={displayedStops} manifestItems={routeItems} savedRoute={isSavedRoute} />
  </div>
}

function ShipmentOperations({ onShipmentSaved }) {
  const { orders, refreshOrders, refreshListings, refreshNotifications, notify } = useApp()
  const [shipments, setShipments] = useState([])
  const [selectedOrderIds, setSelectedOrderIds] = useState([])
  const [loading, setLoading] = useState(true)
  const [workingId, setWorkingId] = useState(null)
  const [apiOffline, setApiOffline] = useState(false)
  const packedOrders = orders.filter((order) => order.stage === 'Packed' && !order.shipmentId && !order.isDisrupted && order.unit === 'kg')

  const refreshShipments = useCallback(async () => {
    try {
      const result = await shipmentService.list()
      setShipments(result.items)
      setApiOffline(result.source !== 'backend')
      return result
    } catch (error) {
      setApiOffline(true)
      throw error
    }
  }, [])

  useEffect(() => {
    let active = true
    shipmentService.list().then((result) => {
      if (!active) return
      setShipments(result.items)
      setApiOffline(result.source !== 'backend')
    }).catch((error) => {
      if (active) {
        setApiOffline(true)
        notify(`Could not load shipments: ${error.message}`, 'error')
      }
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [notify])

  const refreshOperationalData = async () => {
    const results = await Promise.allSettled([refreshOrders(), refreshListings(), refreshNotifications(), refreshShipments()])
    if (results.some((result) => result.status === 'rejected')) {
      notify('The shipment was saved, but some screens could not refresh. Reload to see the latest data.', 'error')
    }
  }

  const createShipment = async () => {
    if (!selectedOrderIds.length || workingId) return
    setWorkingId('create')
    try {
      const shipment = await shipmentService.createFromOrders(selectedOrderIds)
      setShipments((current) => [shipment, ...current.filter((item) => item.id !== shipment.id)])
      onShipmentSaved?.(shipment)
      setSelectedOrderIds([])
      notify(`Shipment ${shipment.id} created with ${shipment.items?.length || 0} order(s).`)
      await refreshOperationalData()
    } catch (error) {
      notify(`Shipment was not created: ${error.message}`, 'error')
    } finally {
      setWorkingId(null)
    }
  }

  const updateShipment = async (shipmentId, operation, status = null) => {
    if (workingId) return
    setWorkingId(shipmentId)
    try {
      const saved = operation === 'cancel'
        ? await shipmentService.cancel(shipmentId)
        : await shipmentService.advanceStage(shipmentId, status)
      setShipments((current) => current.map((shipment) => shipment.id === shipmentId ? saved : shipment))
      onShipmentSaved?.(saved)
      notify(operation === 'cancel' ? `Shipment ${shipmentId} cancelled and inventory released.` : `Shipment ${shipmentId} is now ${saved.status}.`)
      await refreshOperationalData()
    } catch (error) {
      notify(`Shipment update failed: ${error.message}`, 'error')
    } finally {
      setWorkingId(null)
    }
  }

  return <section className="card space-y-4 p-4 sm:p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="font-display text-lg font-bold text-ink-900">Shipment operations</h2>
        <p className="mt-1 text-sm text-ink-500">Assign packed orders, dispatch manifests, report disruptions, and sync delivery status.</p>
      </div>
      {apiOffline && <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">Backend offline · live shipment actions unavailable</span>}
    </div>

    {packedOrders.length > 0 && (
      <div className="rounded-xl border border-ink-100 bg-sand-50/60 p-3">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div><h3 className="text-sm font-semibold text-ink-900">Packed orders awaiting a truck</h3><p className="text-xs text-ink-500">Select kg orders within one vehicle’s capacity.</p></div>
          <Button size="sm" loading={workingId === 'create'} disabled={apiOffline || !selectedOrderIds.length || Boolean(workingId)} onClick={createShipment}>Create shipment</Button>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {packedOrders.map((order) => (
            <label key={order.id} className="flex cursor-pointer items-start gap-2 rounded-lg border border-ink-100 bg-white p-2.5 text-sm">
              <input
                type="checkbox"
                checked={selectedOrderIds.includes(order.id)}
                disabled={apiOffline || Boolean(workingId)}
                onChange={(event) => setSelectedOrderIds((current) => event.target.checked
                  ? [...current, order.id]
                  : current.filter((id) => id !== order.id))}
                className="mt-1 accent-forest-700"
              />
              <span className="min-w-0"><strong className="block truncate text-ink-900">{order.id} · {order.product}</strong><span className="text-xs text-ink-500">{order.quantity} kg · {order.deliveryLocation}</span></span>
            </label>
          ))}
        </div>
      </div>
    )}

    {loading ? <p className="text-sm text-ink-500">Loading saved shipments…</p> : shipments.length === 0 ? (
      <p className="rounded-lg bg-sand-50 p-3 text-sm text-ink-500">No saved shipments yet.</p>
    ) : (
      <div className="grid gap-3 lg:grid-cols-2">
        {shipments.map((shipment) => {
          const nextAction = {
            Confirmed: ['Schedule pickup', 'Scheduled'],
            Scheduled: ['Start transit', 'In Transit'],
            'In Transit': ['Mark delivered', 'Delivered'],
            Disrupted: ['Resume shipment', 'In Transit'],
          }[shipment.status]
          const isWorking = workingId === shipment.id
          return <article key={shipment.id} className="rounded-xl border border-ink-100 p-3.5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div><p className="font-mono text-xs font-semibold text-ink-500">{shipment.id} · {shipment.vehicleName}</p><p className="mt-1 text-sm font-semibold text-ink-900">{shipment.status} · {shipment.currentPayloadKg} kg</p><p className="text-xs text-ink-500">{shipment.origin} → {shipment.destination}</p></div>
              <div className="flex flex-wrap gap-2">
                {shipment.status === 'In Transit' && <Button size="sm" variant="outline" loading={isWorking} disabled={apiOffline || Boolean(workingId)} onClick={() => updateShipment(shipment.id, 'advance', 'Disrupted')}>Report disruption</Button>}
                {nextAction && <Button size="sm" loading={isWorking} disabled={apiOffline || Boolean(workingId)} onClick={() => updateShipment(shipment.id, 'advance', nextAction[1])}>{nextAction[0]}</Button>}
              </div>
            </div>
            {shipment.items?.length > 0 && <p className="mt-2 text-xs text-ink-600">Manifest: {shipment.items.map((item) => `${item.orderId || item.listingId} · ${item.product} · ${item.quantity} ${item.unit}`).join(' | ')}</p>}
            {['Confirmed', 'Scheduled'].includes(shipment.status) && <Button size="sm" variant="outline" className="mt-3" loading={isWorking} disabled={apiOffline || Boolean(workingId)} onClick={() => updateShipment(shipment.id, 'cancel')}>Cancel before departure</Button>}
          </article>
        })}
      </div>
    )}
  </section>
}

function Kpi({ icon: Icon, label, value }) { return <div className="card p-3 flex items-center gap-3"><div className="h-9 w-9 rounded-lg bg-leaf-50 text-forest-700 grid place-items-center"><Icon size={17} /></div><div><p className="text-[11px] text-ink-500">{label}</p><p className="font-display font-bold text-sm text-ink-900">{value}</p></div></div> }
function Metric({ label, value }) { return <div className="flex justify-between gap-3 text-sm"><span className="text-ink-500">{label}</span><span className="font-semibold text-ink-900 text-right">{value}</span></div> }
function StopSelector({ stops, selectedId, onSelect }) { return <div className="card p-4"><h3 className="font-display font-semibold text-sm text-ink-900">Stops</h3><div className="mt-2 space-y-1">{stops.map((stop) => <button key={stop.id} onClick={() => onSelect(stop.id)} className={`w-full flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs ${selectedId === stop.id ? 'bg-leaf-50 text-forest-800' : 'hover:bg-sand-100 text-ink-700'}`}><span className={`grid h-5 w-5 place-items-center rounded-full text-[10px] font-bold text-white ${stop.type === 'pickup' ? 'bg-clay-500' : 'bg-forest-700'}`}>{stop.sequence}</span><span className="min-w-0 truncate font-medium">{stop.name}</span><span className="ml-auto text-ink-500">{stop.eta || 'ETA pending'}</span></button>)}</div></div> }
function RouteDetailsDrawer({ open, onClose, selectedStop, onSelect, stops, manifestItems, savedRoute }) { return <Modal open={open} onClose={onClose} title="Route details" maxWidth="max-w-2xl"><p className="mb-4 text-xs text-ink-500">{savedRoute ? 'Saved shipment manifest and stop sequence' : 'Prototype route simulation · fixed stop sequence'}</p><div className="space-y-3">{stops.map((stop) => { const orders = savedRoute ? (stop.orderIds || []).map((id) => manifestItems.find((item) => item.orderId === id)).filter(Boolean) : getStopOrders(stop); const quantity = orders.reduce((sum, order) => sum + Number(order.quantity ?? order.quantityKg ?? 0), 0); return <button key={stop.id} onClick={() => onSelect(stop.id)} className={`w-full rounded-xl border p-3.5 text-left transition-colors ${selectedStop?.id === stop.id ? 'border-forest-600 bg-leaf-50' : 'border-ink-100 hover:border-forest-400'}`}><div className="flex justify-between gap-3"><div><p className="text-xs font-bold text-forest-700">STOP {stop.sequence} · {stop.type === 'pickup' ? 'PICKUP' : 'DELIVERY'}</p><p className="mt-1 font-display font-semibold text-ink-900">{stop.name}</p><p className="text-xs text-ink-500">{stop.location} · ETA {stop.eta || 'pending'}</p></div><span className="h-fit rounded-md bg-white px-2 py-1 text-xs font-semibold text-ink-700">{stop.status}</span></div><div className="mt-3 grid sm:grid-cols-3 gap-2 text-xs"><Detail label="Orders" value={orders.length ? orders.map((order) => order.orderId || order.id).join(', ') : 'Consolidated cargo'} /><Detail label="Produce" value={orders.length ? orders.map((order) => order.product).join(', ') : 'Mixed load'} /><Detail label="Quantity" value={orders.length ? `${quantity} kg` : '—'} /></div></button> })}</div></Modal> }
function Detail({ label, value }) { return <div><p className="text-ink-500">{label}</p><p className="mt-0.5 font-medium text-ink-900">{value}</p></div> }
