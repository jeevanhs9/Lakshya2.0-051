import { useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import { useApp } from '../../context/useApp'
import Toast from '../ui/Toast'
import { useTranslation } from 'react-i18next'

const TITLE_KEYS = {
  '/farmer': 'routes.farmerDashboard', '/farmer/products': 'ui.myProducts', '/farmer/listing/new': 'ui.addNewListing',
  '/farmer/orders': 'ui.orders', '/farmer/insights': 'ui.aiInsights', '/farmer/pooling': 'routes.intelligentLoadPooling',
  '/farmer/offers': 'routes.buyerOffersNetProceeds', '/farmer/profile': 'ui.profile', '/buyer': 'ui.marketplace',
  '/buyer/cart': 'routes.shoppingCart', '/buyer/checkout': 'ui.checkout', '/buyer/orders': 'ui.myOrders',
  '/buyer/profile': 'ui.profile', '/logistics': 'ui.logisticsDashboard', '/logistics/routes': 'ui.routeDetails',
  '/logistics/pooling': 'routes.loadPoolingCoordination', '/logistics/profile': 'ui.profile', '/admin': 'routes.platformOverview',
  '/admin/farmers': 'ui.farmersFpos', '/admin/buyers': 'ui.buyers', '/admin/orders': 'routes.platformOrders',
  '/admin/analytics': 'routes.platformAnalytics', '/admin/enterprise': 'routes.sapEnterpriseGateway',
  '/admin/profile': 'ui.profile', '/disruptions': 'routes.disruptionRecovery',
}

function titleFor(pathname, t) {
  if (TITLE_KEYS[pathname]) return t(TITLE_KEYS[pathname])
  if (pathname.startsWith('/buyer/product/')) return t('routes.productDetails')
  return t('ui.appName')
}

export default function DashboardLayout({ allowedRole }) {
  const { user, toast, dismissToast } = useApp()
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const { t } = useTranslation()

  if (!user) return <Navigate to="/login" replace />
  const isAllowed = !allowedRole || user.role === allowedRole || (allowedRole === 'farmer' && user.role === 'fpo')
  if (!isAllowed) return <Navigate to={`/${user.role === 'fpo' ? 'farmer' : user.role}`} replace />

  return (
    <div className="min-h-screen flex bg-sand-50 selection:bg-leaf-300 selection:text-ink-900">
      <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      <div className="flex-1 min-w-0 flex flex-col relative">
        <Topbar title={titleFor(location.pathname, t)} onMenuClick={() => setMobileOpen(true)} />
        <main className="flex-1 p-4 lg:p-7 max-w-[1400px] w-full mx-auto relative z-0 animate-fade-up">
          <Outlet />
        </main>
        <Toast toast={toast} onDismiss={dismissToast} />
      </div>
    </div>
  )
}
