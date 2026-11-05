import { useCallback, useEffect, useMemo, useState } from 'react'
import { products as seedProducts } from '../data/products'
import { orders as seedOrders, ORDER_STAGES } from '../data/orders'
import { demoUsers } from '../data/users'
import { AppContext } from './contextStore'
import { authService, productService, orderService, notificationService } from '../services/api'

function loadDemoState(key, fallback) {
  try {
    const saved = window.localStorage.getItem(key)
    if (!saved) return fallback
    const parsed = JSON.parse(saved)
    return parsed !== null && parsed !== undefined ? parsed : fallback
  } catch {
    return fallback
  }
}

function saveDemoState(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Graceful silent fallback
  }
}

export function AppProvider({ children }) {
  const [user, setUser] = useState(() => loadDemoState('farmlink-user', null))
  const [listings, setListings] = useState(() => loadDemoState('farmlink-listings', seedProducts))
  const [orders, setOrders] = useState(() => loadDemoState('farmlink-orders', seedOrders))
  const [cart, setCart] = useState(() => loadDemoState('farmlink-cart', []))
  const [notifications, setNotifications] = useState([])
  const [toast, setToast] = useState(null)

  useEffect(() => { saveDemoState('farmlink-user', user) }, [user])
  useEffect(() => { saveDemoState('farmlink-listings', listings) }, [listings])
  useEffect(() => { saveDemoState('farmlink-orders', orders) }, [orders])
  useEffect(() => { saveDemoState('farmlink-cart', cart) }, [cart])

  const notify = useCallback((message, tone = 'success') => {
    setToast({ message, tone, id: Date.now() })
  }, [])

  const refreshListings = useCallback(async () => {
    const { items, source } = await productService.list()
    if (source === 'backend') setListings(items)
    else setListings((current) => current.length ? current : items)
    return items
  }, [])

  const refreshOrders = useCallback(async () => {
    const filters = user?.role === 'buyer'
      ? { buyerId: user.id }
      : ['farmer', 'fpo'].includes(user?.role)
        ? { farmerId: user.id }
        : {}
    const { items, source } = await orderService.list(filters)
    if (source === 'backend') setOrders(items)
    else setOrders((current) => current.length ? current : items)
    return items
  }, [user])

  const refreshNotifications = useCallback(async () => {
    const items = await notificationService.list(user?.role, user?.id)
    setNotifications(items || [])
    return items
  }, [user])

  // Initial fetch from backend if active
  useEffect(() => {
    let mounted = true
    productService.list().then(({ items, source }) => {
      if (!mounted) return
      if (source === 'backend') setListings(items)
      else setListings((current) => current.length ? current : items)
    }).catch((error) => {
      if (mounted) notify(`Could not load listings: ${error.message}`, 'error')
    })

    const filters = user?.role === 'buyer'
      ? { buyerId: user.id }
      : ['farmer', 'fpo'].includes(user?.role)
        ? { farmerId: user.id }
        : {}
    orderService.list(filters).then(({ items, source }) => {
      if (!mounted) return
      if (source === 'backend') setOrders(items)
      else setOrders((current) => current.length ? current : items)
    }).catch((error) => {
      if (mounted) notify(`Could not load orders: ${error.message}`, 'error')
    })

    notificationService.list(user?.role, user?.id).then((notifs) => {
      if (mounted && notifs) setNotifications(notifs)
    }).catch((error) => {
      if (mounted) notify(`Could not load notifications: ${error.message}`, 'error')
    })

    return () => { mounted = false }
  }, [notify, user])

  const login = useCallback(async (role) => {
    if (!demoUsers[role]) return null
    try {
      const authenticatedUser = await authService.demoLogin(role)
      setUser(authenticatedUser)
      return authenticatedUser
    } catch (error) {
      notify(`Sign-in failed: ${error.message}`, 'error')
      return null
    }
  }, [notify])

  const logout = useCallback(() => {
    setUser(null)
    setCart([])
    try { window.localStorage.removeItem('farmlink-user') } catch {}
  }, [])

  const addListing = useCallback(async (listing) => {
    const newListing = {
      farmerId: user?.id ?? 'f1',
      farmer: user?.orgName ?? "Farmer's Listing",
      demand: 'Medium',
      image: listing.image || 'https://images.unsplash.com/photo-1592841200221-a6898f307baa?q=80&w=800&auto=format&fit=crop',
      ...listing,
      location: listing.location?.trim() || user?.location || 'Kolar, Karnataka',
    }
    try {
      const savedListing = await productService.create(newListing)
      setListings((prev) => [savedListing, ...prev.filter((item) => item.id !== savedListing.id)])
      notify(`${savedListing.name} has been added to your listings.`)
      return savedListing
    } catch (error) {
      notify(`Listing was not saved: ${error.message}`, 'error')
      return null
    }
  }, [user, notify])

  const editListing = useCallback(async (listingId, updates) => {
    try {
      const savedListing = await productService.update(listingId, updates)
      setListings((prev) => prev.map((item) => item.id === listingId ? savedListing : item))
      notify('Produce listing updated successfully.')
      return savedListing
    } catch (error) {
      notify(`Listing was not updated: ${error.message}`, 'error')
      return null
    }
  }, [notify])

  const deleteListing = useCallback(async (listingId) => {
    try {
      await productService.delete(listingId)
      setListings((prev) => prev.filter((item) => item.id !== listingId))
      notify('Listing deactivated and removed from active marketplace.', 'info')
      return true
    } catch (error) {
      notify(`Listing was not deactivated: ${error.message}`, 'error')
      return false
    }
  }, [notify])

  const addToCart = useCallback((productId, quantity) => {
    const product = listings.find((item) => item.id === productId)
    if (!product || product.quantity <= 0) {
      notify('This listing is no longer available.', 'error')
      return
    }
    const requested = Math.max(1, Math.floor(Number(quantity) || 0))
    const existing = cart.find((item) => item.productId === productId)
    const remaining = product.quantity - (existing?.quantity ?? 0)
    const accepted = Math.min(requested, Math.max(0, remaining))
    if (accepted <= 0) {
      notify(`Only ${product.quantity} ${product.unit} are available.`, 'error')
      return
    }
    setCart((prev) => {
      const current = prev.find((item) => item.productId === productId)
      return current
        ? prev.map((item) => item.productId === productId ? { ...item, quantity: item.quantity + accepted } : item)
        : [...prev, { productId, quantity: accepted }]
    })
    notify(accepted < requested
      ? `Added the available ${accepted} ${product.unit} of ${product.name}.`
      : `${product.name} added to cart.`)
  }, [cart, listings, notify])

  const updateCartQuantity = useCallback((productId, quantity) => {
    const product = listings.find((item) => item.id === productId)
    if (!product) {
      setCart((prev) => prev.filter((item) => item.productId !== productId))
      return
    }
    if (quantity > product.quantity) {
      quantity = product.quantity
      notify(`Only ${product.quantity} ${product.unit} are available.`)
    }
    setCart((prev) => {
      if (quantity <= 0) return prev.filter((item) => item.productId !== productId)
      return prev.map((item) => item.productId === productId ? { ...item, quantity } : item)
    })
  }, [listings, notify])

  const removeFromCart = useCallback((productId) => {
    setCart((prev) => prev.filter((item) => item.productId !== productId))
  }, [])

  const clearCart = useCallback(() => setCart([]), [])

  const cartItems = useMemo(() => cart.map((item) => {
    const product = listings.find((listing) => listing.id === item.productId)
    return product ? { ...item, product } : null
  }).filter(Boolean), [cart, listings])

  const cartCount = useMemo(() => cart.length, [cart])

  const placeOrder = useCallback(async (deliveryLocation, paymentMethod) => {
    const validItems = cartItems.filter((item) => item.quantity > 0 && item.quantity <= item.product.quantity)
    if (!validItems.length || validItems.length !== cartItems.length) {
      notify('Review your cart quantities before placing the order.', 'error')
      return []
    }

    try {
      const createdOrders = await orderService.placeOrder({
        items: validItems.map((item) => ({ productId: item.product.id, quantity: item.quantity })),
        buyerId: user?.id,
        deliveryLocation: deliveryLocation.trim(),
        paymentMethod,
      })
      const purchased = new Map(validItems.map((item) => [item.product.id, item.quantity]))
      setOrders((prev) => [...createdOrders, ...prev.filter((order) => !createdOrders.some((saved) => saved.id === order.id))])
      setListings((prev) => prev.map((product) => purchased.has(product.id)
        ? { ...product, quantity: Math.max(0, product.quantity - purchased.get(product.id)) }
        : product))
      clearCart()
      notify(`${createdOrders.length} order${createdOrders.length === 1 ? '' : 's'} placed successfully.`)
      return createdOrders
    } catch (error) {
      notify(`Order was not placed: ${error.message}`, 'error')
      return []
    }
  }, [cartItems, user, clearCart, notify])

  const advanceOrderStage = useCallback(async (orderId) => {
    const order = orders.find((item) => item.id === orderId)
    if (!order) return null
    const index = ORDER_STAGES.indexOf(order.stage)
    if (index < 0 || index >= ORDER_STAGES.length - 1) return null
    const nextStage = ORDER_STAGES[index + 1]
    try {
      const savedOrder = await orderService.advanceStage(orderId, nextStage)
      setOrders((prev) => prev.map((item) => item.id === orderId ? savedOrder : item))
      return savedOrder
    } catch (error) {
      notify(`Order status was not updated: ${error.message}`, 'error')
      return null
    }
  }, [orders, notify])

  const cancelOrder = useCallback(async (orderId, reason = 'Buyer cancellation request') => {
    try {
      const response = await orderService.cancelOrder(orderId, reason)
      setOrders((prev) => prev.map((order) => order.id === orderId ? response.order : order))
      notify(`Order ${orderId} has been cancelled and recorded.`, 'info')
      refreshListings().catch((error) => notify(`Order cancelled, but inventory could not refresh: ${error.message}`, 'error'))
      refreshNotifications().catch((error) => notify(`Order cancelled, but notifications could not refresh: ${error.message}`, 'error'))
      return response
    } catch (error) {
      notify(`Order was not cancelled: ${error.message}`, 'error')
      return null
    }
  }, [notify, refreshListings, refreshNotifications])

  const markNotificationRead = useCallback(async (id) => {
    try {
      await notificationService.markRead(id)
      setNotifications((prev) => prev.map((n) => n.id === id ? { ...n, isRead: true } : n))
    } catch (error) {
      notify(`Notification was not marked read: ${error.message}`, 'error')
    }
  }, [notify])

  const unreadNotificationsCount = useMemo(() => {
    return notifications.filter(n => !n.isRead).length
  }, [notifications])

  const value = {
    user, login, logout,
    listings, addListing, editListing, deleteListing, refreshListings,
    orders, advanceOrderStage, cancelOrder,
    refreshOrders, refreshNotifications,
    cart, cartItems, cartCount, addToCart, updateCartQuantity, removeFromCart, clearCart, placeOrder,
    notifications, unreadNotificationsCount, markNotificationRead,
    toast, dismissToast: () => setToast(null), notify,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
