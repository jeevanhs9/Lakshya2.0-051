import { useState } from 'react'
import { useApp } from '../../context/useApp'
import { ORDER_STAGES } from '../../data/orders'
import OrderTable from '../../components/orders/OrderTable'
import OrderTimeline from '../../components/orders/OrderTimeline'
import Modal from '../../components/ui/Modal'
import Button from '../../components/ui/Button'
import EmptyState from '../../components/ui/EmptyState'
import Badge from '../../components/ui/Badge'
import { ClipboardList, ArrowRight } from 'lucide-react'
import { formatDate, formatINR } from '../../utils/format'

const STAGE_TONE = {
  'Order Placed': 'info', Confirmed: 'medium', Packed: 'medium',
  'Picked Up': 'medium', 'In Transit': 'medium', Delivered: 'success', Cancelled: 'error',
}

function nextStage(stage) {
  const idx = ORDER_STAGES.indexOf(stage)
  return ORDER_STAGES[Math.min(idx + 1, ORDER_STAGES.length - 1)]
}

export default function FarmerOrders() {
  const { user, orders, advanceOrderStage } = useApp()
  const [selected, setSelected] = useState(null)
  const [advancing, setAdvancing] = useState(false)
  const myOrders = orders.filter((o) => o.farmerId === user.id)
  const active = myOrders.filter((o) => !['Delivered', 'Cancelled'].includes(o.stage))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink-900 tracking-tight">Orders</h2>
          <p className="text-sm font-medium text-ink-500 mt-1">
            {myOrders.length} total · {active.length} active
          </p>
        </div>
      </div>

      {myOrders.length ? (
        <OrderTable
          orders={myOrders}
          columns={['id', 'buyer', 'product', 'quantity', 'total', 'stage', 'placedOn']}
          onRowClick={setSelected}
        />
      ) : (
        <EmptyState
          icon={ClipboardList}
          title="No orders yet"
          description="Orders for your listings will appear here once buyers place them."
        />
      )}

      <Modal open={!!selected} onClose={() => setSelected(null)} title={`Order ${selected?.id}`} maxWidth="max-w-2xl">
        {selected && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              {[
                { label: 'Buyer', value: selected.buyer },
                { label: 'Product', value: selected.product },
                { label: 'Quantity', value: `${selected.quantity} ${selected.unit}` },
                { label: 'Order Value', value: formatINR(selected.total) },
                { label: 'Placed On', value: formatDate(selected.placedOn) },
                { label: 'Expected ETA', value: formatDate(selected.eta) },
              ].map(({ label, value }) => (
                <div key={label} className="bg-sand-50 rounded-xl p-3 border border-ink-100">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-ink-500 mb-1">{label}</p>
                  <p className="font-semibold text-ink-900 text-sm">{value}</p>
                </div>
              ))}
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-bold uppercase tracking-wider text-ink-500">Order Progress</p>
                <Badge tone={STAGE_TONE[selected.stage]} rounded="rounded-full">{selected.stage}</Badge>
              </div>
              <OrderTimeline currentStage={selected.stage} />
            </div>

            {['Order Placed', 'Confirmed'].includes(selected.stage) && !selected.shipmentId && (
              <div className="flex items-center justify-between pt-4 border-t border-ink-100">
                <p className="text-sm font-medium text-ink-500">
                  Next stage: <span className="font-bold text-ink-900">{nextStage(selected.stage)}</span>
                </p>
                <Button
                  size="sm"
                  loading={advancing}
                  onClick={async () => {
                    if (advancing) return
                    setAdvancing(true)
                    try {
                      const savedOrder = await advanceOrderStage(selected.id)
                      if (savedOrder) setSelected(savedOrder)
                    } finally {
                      setAdvancing(false)
                    }
                  }}
                >
                  {!advancing && <>Advance Stage <ArrowRight size={14} className="ml-1.5" /></>}
                </Button>
              </div>
            )}
            {selected.stage === 'Packed' && !selected.shipmentId && (
              <p className="border-t border-ink-100 pt-4 text-sm text-ink-500">Packed and awaiting shipment assignment from the logistics workspace.</p>
            )}
            {selected.shipmentId && !['Delivered', 'Cancelled'].includes(selected.stage) && (
              <p className="border-t border-ink-100 pt-4 text-sm text-ink-500">Shipment {selected.shipmentId} controls pickup and delivery updates.</p>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
