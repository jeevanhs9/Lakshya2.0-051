import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, MapPin, Truck, CreditCard, ArrowRight, ShoppingBag, ShieldCheck, Smartphone, Landmark } from 'lucide-react'
import { useApp } from '../../context/useApp'
import { useTranslation } from 'react-i18next'
import Button from '../../components/ui/Button'
import EmptyState from '../../components/ui/EmptyState'
import Modal from '../../components/ui/Modal'
import { formatINR } from '../../utils/format'
import { calculateOrderSummary } from '../../utils/pricing'

const PAYMENT_METHODS = ['UPI', 'Credit / Debit Card', 'Net Banking', 'Cash on Delivery']

export default function Checkout() {
  const { cartItems, placeOrder } = useApp()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [location, setLocation] = useState('')
  const [payment, setPayment] = useState('UPI')
  const [placingOrder, setPlacingOrder] = useState(false)
  const [confirmedOrders, setConfirmedOrders] = useState(null)
  const [paymentOpen, setPaymentOpen] = useState(false)
  const [paymentStatus, setPaymentStatus] = useState('idle')
  const [paymentReference, setPaymentReference] = useState('')

  if (cartItems.length === 0 && !confirmedOrders) {
    return (
      <EmptyState
        icon={ShoppingBag}
        title="Nothing to check out"
        description="Add produce to your cart first."
        action={<Button onClick={() => navigate('/buyer')}>Go to Marketplace</Button>}
      />
    )
  }

  const { subtotal, logistics, platformFee, total } = calculateOrderSummary(cartItems)

  const handlePlaceOrder = async (event) => {
    event.preventDefault()
    if (placingOrder) return
    setPlacingOrder(true)
    try {
      const created = await placeOrder(location, payment)
      if (created.length) setConfirmedOrders(created)
    } finally {
      setPlacingOrder(false)
    }
  }

  const openPayment = () => {
    if (location.trim().length < 5 || placingOrder) return
    setPaymentStatus('idle')
    setPaymentOpen(true)
  }

  const confirmDemoPayment = async () => {
    if (paymentStatus === 'processing') return
    setPaymentStatus('processing')
    // This visual delay deliberately simulates a gateway response only. No
    // card, UPI, bank, or personal payment data is collected or transmitted.
    await new Promise((resolve) => window.setTimeout(resolve, 850))
    setPaymentReference(`DEMO-${Date.now().toString().slice(-8)}`)
    setPaymentStatus('approved')
  }

  const finishDemoCheckout = async () => {
    setPaymentOpen(false)
    await handlePlaceOrder({ preventDefault: () => {} })
  }

  if (confirmedOrders) {
    return (
      <div className="max-w-lg mx-auto">
        <div className="card p-8 text-center bg-white relative overflow-hidden">
          <div className="absolute inset-0 bg-leaf-50/50" />
          <div className="relative z-10">
            <div className="h-16 w-16 rounded-full bg-forest-100 text-forest-700 flex items-center justify-center mx-auto mb-5 shadow-lg shadow-forest-200/50">
              <CheckCircle2 size={32} strokeWidth={2.5} />
            </div>
            <h2 className="font-display text-2xl font-bold text-ink-900 tracking-tight">{t('checkout.orderConfirmed')}</h2>
            <p className="text-sm text-ink-500 mt-2 max-w-xs mx-auto">
              {t('checkout.ordersPlaced', { count: confirmedOrders.length })}
            </p>

            <div className="mt-6 rounded-xl bg-sand-50 px-4 py-3 text-left border border-ink-100">
              <div className="flex items-center gap-2 mb-2">
                <MapPin size={14} className="text-forest-600" />
                <span className="text-xs font-bold uppercase tracking-wider text-ink-500">{t('checkout.deliveryTo')}</span>
              </div>
              <p className="text-sm font-semibold text-ink-900">{confirmedOrders[0]?.deliveryLocation}</p>
            </div>

            <div className="mt-4 space-y-3">
              {confirmedOrders.map((o) => (
                <div key={o.id} className="flex justify-between items-center text-sm border border-ink-100 rounded-xl px-4 py-3 bg-white">
                  <div>
                    <span className="font-display font-bold text-ink-900">{o.id}</span>
                    <span className="text-ink-500 mx-2">·</span>
                    <span className="font-medium text-ink-700">{o.product}</span>
                  </div>
                  <span className="font-display font-bold text-forest-700">{formatINR(o.total)}</span>
                </div>
              ))}
            </div>
            {paymentReference && <p className="mt-4 text-xs font-medium text-forest-700">{t('checkout.paymentReference')} {paymentReference}</p>}

            <div className="flex justify-center gap-3 mt-8">
              <Button variant="outline" onClick={() => navigate('/buyer')} className="px-5">
                {t('checkout.continueShopping')}
              </Button>
              <Button onClick={() => navigate('/buyer/orders')} className="px-5">
                {t('checkout.trackOrders')} <ArrowRight size={16} className="ml-2" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={(event) => { event.preventDefault(); openPayment() }} className="grid lg:grid-cols-[1fr_400px] gap-6 lg:gap-8 items-start">
      <div className="space-y-5">
        <div className="card p-6 bg-white">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="h-8 w-8 rounded-lg bg-leaf-50 text-forest-700 flex items-center justify-center border border-leaf-100">
              <MapPin size={18} />
            </div>
            <h3 className="font-display font-bold text-base text-ink-900 tracking-tight">{t('checkout.deliveryAddress')}</h3>
          </div>
          <label htmlFor="delivery-location" className="sr-only">{t('checkout.deliveryLocation')}</label>
          <input
            id="delivery-location"
            required
            minLength={5}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder={t('checkout.addressPlaceholder')}
            className="w-full px-4 py-3 rounded-xl border border-ink-200 text-[15px] bg-sand-50/50 focus:bg-white focus-ring focus:border-forest-500 transition-all"
          />
        </div>

        <div className="card p-6 bg-white">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="h-8 w-8 rounded-lg bg-leaf-50 text-forest-700 flex items-center justify-center border border-leaf-100">
              <Truck size={18} />
            </div>
            <h3 className="font-display font-bold text-base text-ink-900 tracking-tight">{t('checkout.deliveryTimeline')}</h3>
          </div>
          <p className="text-sm text-ink-600 leading-relaxed">
            {t('checkout.deliveryEstimate')}
          </p>
          <div className="mt-4 flex items-center gap-2 text-xs font-medium text-forest-700 bg-leaf-50 px-3 py-2 rounded-lg border border-leaf-100">
            <Truck size={14} />
            <span>{t('checkout.ecoDelivery')}</span>
          </div>
        </div>

        <div className="card p-6 bg-white">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="h-8 w-8 rounded-lg bg-leaf-50 text-forest-700 flex items-center justify-center border border-leaf-100">
              <CreditCard size={18} />
            </div>
            <h3 className="font-display font-bold text-base text-ink-900 tracking-tight">{t('checkout.paymentMethod')}</h3>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {PAYMENT_METHODS.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setPayment(m)}
                aria-pressed={payment === m}
                className={`px-4 py-3 rounded-xl border text-sm font-bold text-left transition-all focus-ring
                  ${payment === m
                    ? 'border-forest-600 bg-leaf-50 text-forest-800 ring-2 ring-forest-200'
                    : 'border-ink-200 text-ink-700 hover:border-forest-400 hover:bg-sand-50'
                  }`}
              >
                <span className="block">{t(`checkout.${({ UPI: 'upi', 'Credit / Debit Card': 'card', 'Net Banking': 'netBanking', 'Cash on Delivery': 'cashOnDelivery' })[m]}`)}</span>
              </button>
            ))}
          </div>
          <p className="text-[11px] text-ink-400 mt-4 flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-ink-300" />
            {t('checkout.prototypeNotice')}
          </p>
        </div>
      </div>

      <div className="card p-6 bg-white sticky top-[84px]">
        <h3 className="font-display font-bold text-lg text-ink-900 mb-5 tracking-tight">{t('checkout.orderSummary')}</h3>

        <div className="space-y-3 max-h-[200px] overflow-y-auto pr-2 -mx-1 px-1">
          {cartItems.map(({ product, quantity }) => (
            <div key={product.id} className="flex items-center gap-3 text-sm">
              <img src={product.image} alt="" className="h-10 w-10 rounded-lg object-cover border border-ink-100" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-ink-900 truncate">{product.name}</p>
                <p className="text-xs text-ink-500">{quantity} × {product.unit}</p>
              </div>
              <span className="font-display font-bold text-ink-900">{formatINR(product.price * quantity)}</span>
            </div>
          ))}
        </div>

        <dl className="mt-5 space-y-3 text-sm border-t border-ink-100 pt-4">
          <div className="flex justify-between items-center">
            <dt className="text-ink-600 font-medium">{t('checkout.subtotal')}</dt>
            <dd className="font-bold text-ink-900">{formatINR(subtotal)}</dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-ink-600 font-medium">{t('checkout.logisticsFee')}</dt>
            <dd className="font-bold text-ink-900">{formatINR(logistics)}</dd>
          </div>
          <div className="flex justify-between items-center">
            <dt className="text-ink-600 font-medium">{t('checkout.platformFee')}</dt>
            <dd className="font-bold text-ink-900">{formatINR(platformFee)}</dd>
          </div>
          <div className="flex justify-between items-center pt-3 border-t border-ink-100">
            <dt className="font-display font-bold text-base text-ink-900">{t('checkout.totalToPay')}</dt>
            <dd className="font-display font-bold text-2xl text-forest-700 tracking-tight">{formatINR(total)}</dd>
          </div>
        </dl>

        <Button
          type="submit"
          className="w-full mt-6 py-3.5 text-[15px] flex justify-between items-center"
          disabled={location.trim().length < 5 || placingOrder}
          loading={placingOrder}
        >
          {placingOrder ? t('checkout.creatingOrder') : t('checkout.reviewAndPay')}
          {!placingOrder && <ArrowRight size={18} />}
        </Button>
      </div>

      <Modal open={paymentOpen} onClose={() => paymentStatus !== 'processing' && setPaymentOpen(false)} title={t('checkout.gatewayTitle')} maxWidth="max-w-md">
        <div className="space-y-5">
          <div className="rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <strong>{t('checkout.prototypeOnly')}</strong> {t('checkout.gatewayWarning')}
          </div>

          {paymentStatus === 'approved' ? (
            <div className="text-center py-3">
              <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-leaf-50 text-forest-700"><CheckCircle2 size={30} /></div>
              <h3 className="font-display text-lg font-bold text-ink-900">{t('checkout.paymentApproved')}</h3>
              <p className="mt-1 text-sm text-ink-500">{t('checkout.reference')} {paymentReference}</p>
              <Button type="button" className="mt-5 w-full" onClick={finishDemoCheckout}>{t('checkout.createDemoOrder')} <ArrowRight size={16} className="ml-2" /></Button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between rounded-xl border border-ink-100 bg-sand-50 p-4">
                <div><p className="text-xs font-bold uppercase tracking-wide text-ink-500">{t('checkout.amountToSimulate')}</p><p className="mt-1 font-display text-2xl font-bold text-forest-700">{formatINR(total)}</p></div>
                <ShieldCheck className="text-forest-600" size={30} />
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs font-semibold text-ink-600">
                <span className="rounded-lg border border-ink-100 p-3"><Smartphone className="mx-auto mb-1 text-forest-600" size={18} />UPI</span>
                <span className="rounded-lg border border-ink-100 p-3"><CreditCard className="mx-auto mb-1 text-forest-600" size={18} />Card</span>
                <span className="rounded-lg border border-ink-100 p-3"><Landmark className="mx-auto mb-1 text-forest-600" size={18} />Bank</span>
              </div>
              <p className="text-sm text-ink-600">{t('checkout.selectedMethod')} <strong>{t(`checkout.${({ UPI: 'upi', 'Credit / Debit Card': 'card', 'Net Banking': 'netBanking', 'Cash on Delivery': 'cashOnDelivery' })[payment]}`)}</strong>. {t('checkout.localApproval')}</p>
              <Button type="button" className="w-full" loading={paymentStatus === 'processing'} onClick={confirmDemoPayment}>{paymentStatus === 'processing' ? t('checkout.simulatingPayment') : t('checkout.simulatePayment', { amount: formatINR(total) })}</Button>
            </>
          )}
        </div>
      </Modal>
    </form>
  )
}
